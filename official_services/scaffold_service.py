"""
Scaffold service: generate skill YAML from a natural-language intent.

This module is the pythoncall backend for the `skill.generate-from-prompt`
capability.  It can operate in two modes:

1. **LLM mode** (default when OPENAI_API_KEY is set): sends a structured
   prompt to an OpenAI-compatible chat endpoint and parses the YAML response.

2. **Template mode** (fallback): performs keyword-based capability matching
   and emits a well-formed skeleton with the most relevant capabilities.

The output is always validated against the skill schema before returning.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Catalog loader
# ---------------------------------------------------------------------------

def _find_registry_root(hint: str | None) -> Path | None:
    """
    Try to locate the agent-skill-registry root.

    Resolution order:
    1. Explicit hint argument
    2. AGENT_SKILL_REGISTRY_ROOT env var
    3. Sibling of the agent-skills repo root (../agent-skill-registry)
    4. Current working directory parent
    """
    if hint:
        p = Path(hint)
        if p.is_dir():
            return p

    env = os.environ.get("AGENT_SKILL_REGISTRY_ROOT")
    if env:
        p = Path(env)
        if p.is_dir():
            return p

    # __file__ is .../agent-skills/official_services/scaffold_service.py
    agent_skills_root = Path(__file__).resolve().parent.parent
    sibling = agent_skills_root.parent / "agent-skill-registry"
    if sibling.is_dir():
        return sibling

    cwd_sibling = Path.cwd().parent / "agent-skill-registry"
    if cwd_sibling.is_dir():
        return cwd_sibling

    return None


def _load_capabilities(registry_root: Path) -> list[dict[str, Any]]:
    catalog_path = registry_root / "catalog" / "capabilities.json"
    if not catalog_path.exists():
        return []
    with catalog_path.open(encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("capabilities", [])
    return []


# ---------------------------------------------------------------------------
# ID / slug helpers
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "it", "its", "that", "this",
    "then", "when", "if", "so", "via", "into", "out",
}

# Maps intent keywords → capability domains (for template mode)
_DOMAIN_HINTS: dict[str, list[str]] = {
    "email": ["email"],
    "mail": ["email"],
    "pdf": ["pdf"],
    "invoice": ["pdf", "text"],
    "document": ["doc"],
    "text": ["text"],
    "summarize": ["text"],
    "summary": ["text"],
    "translate": ["text"],
    "classify": ["text"],
    "extract": ["text"],
    "entity": ["text"],
    "keyword": ["text"],
    "language": ["text"],
    "embed": ["text"],
    "image": ["image"],
    "photo": ["image"],
    "audio": ["audio"],
    "transcribe": ["audio"],
    "memory": ["memory"],
    "store": ["memory"],
    "retrieve": ["memory"],
    "data": ["data"],
    "json": ["data"],
    "schema": ["data"],
    "table": ["table"],
    "web": ["web"],
    "fetch": ["web"],
    "search": ["web"],
    "url": ["web"],
    "page": ["web"],
    "code": ["code"],
    "diff": ["code"],
    "format": ["code"],
    "agent": ["agent"],
    "route": ["agent"],
    "delegate": ["agent"],
    "plan": ["agent"],
    "security": ["security"],
    "pii": ["security"],
    "secret": ["security"],
    "policy": ["policy"],
    "message": ["message"],
    "send": ["message"],
    "ops": ["ops"],
    "budget": ["ops"],
    "trace": ["ops"],
    "task": ["task"],
    "ticket": ["task"],
    "assign": ["task"],
    "close": ["task"],
    "approve": ["task"],
    "identity": ["identity"],
    "role": ["identity"],
    "permission": ["identity"],
    "integration": ["integration"],
    "sync": ["integration"],
    "connector": ["integration"],
}


def _suggest_id(intent: str) -> str:
    """Derive a domain.slug id from the intent string."""
    words = re.findall(r"[a-z]+", intent.lower())
    content_words = [w for w in words if w not in _STOP_WORDS]

    # Guess domain from first content keyword that maps to a known domain
    domain = "workflow"
    for w in content_words:
        if w in _DOMAIN_HINTS:
            domain = _DOMAIN_HINTS[w][0]
            break

    # Build slug from first 3 meaningful content words, avoiding domain repeat
    slug_words = [w for w in content_words if w != domain][:3]
    slug = "-".join(slug_words) if slug_words else "custom"
    return f"{domain}.{slug}"


def _rank_capabilities(
    intent: str,
    capabilities: list[dict[str, Any]],
    top_n: int = 8,
) -> list[dict[str, Any]]:
    """
    Score capabilities by keyword overlap with the intent (template mode).

    Strategy:
    1. Collect all domains mentioned in the intent.
    2. For each mentioned domain, pick the best 1-2 capabilities from that domain.
    3. Fill remaining slots with highest-overlap capabilities.
    """
    intent_words = set(re.findall(r"[a-z]+", intent.lower())) - _STOP_WORDS

    # Phase 1: determine which domains are explicitly mentioned
    mentioned_domains: list[str] = []
    for w in re.findall(r"[a-z]+", intent.lower()):
        for d in _DOMAIN_HINTS.get(w, []):
            if d not in mentioned_domains:
                mentioned_domains.append(d)

    # Index capabilities by domain
    by_domain: dict[str, list[dict[str, Any]]] = {}
    for cap in capabilities:
        cap_id = cap.get("id", "")
        domain = cap_id.split(".")[0]
        by_domain.setdefault(domain, []).append(cap)

    def _cap_score(cap: dict[str, Any]) -> int:
        cap_id = cap.get("id", "")
        cap_words = set(re.findall(r"[a-z]+", (cap_id + " " + cap.get("description", "")).lower()))
        return len(intent_words & cap_words)

    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    # Phase 2: domain-first — give one representative cap per mentioned domain
    for domain in mentioned_domains:
        domain_caps = by_domain.get(domain, [])
        if not domain_caps:
            continue
        best = sorted(domain_caps, key=_cap_score, reverse=True)[0]
        if best.get("id") not in seen_ids:
            selected.append(best)
            seen_ids.add(best.get("id", ""))
        if len(selected) >= top_n:
            break

    # Phase 3: fill remaining slots by overall word overlap
    if len(selected) < top_n:
        scored = sorted(
            [(c, _cap_score(c)) for c in capabilities if c.get("id") not in seen_ids],
            key=lambda x: -x[1],
        )
        for cap, score in scored:
            if score == 0 and len(selected) >= 2:
                break
            selected.append(cap)
            seen_ids.add(cap.get("id", ""))
            if len(selected) >= top_n:
                break

    return selected[:top_n] if selected else capabilities[:3]


# ---------------------------------------------------------------------------
# Template-mode generator
# ---------------------------------------------------------------------------

def _build_template_skill(
    intent: str,
    suggested_id: str,
    matched_caps: list[dict[str, Any]],
    target_channel: str,
) -> str:
    """Build a well-formed but stub skill YAML without an LLM."""
    parts = suggested_id.split(".", 1)
    slug = parts[1] if len(parts) > 1 else suggested_id
    name = slug.replace("-", " ").title()

    steps = []
    prev_ref = "inputs.input_text"
    for i, cap in enumerate(matched_caps[:4]):
        cap_id = cap.get("id", "unknown")
        step_id = f"{cap_id.replace('.', '_')}_step{i + 1}"
        is_last = i == len(matched_caps[:4]) - 1

        cap_in_fields = list(cap.get("inputs", {}).keys())
        cap_out_fields = list(cap.get("outputs", {}).keys())
        first_in = cap_in_fields[0] if cap_in_fields else "text"
        first_out = cap_out_fields[0] if cap_out_fields else "result"

        local_alias = "outputs.result" if is_last else f"{step_id}_{first_out}"

        steps.append({
            "id": step_id,
            "uses": cap_id,
            "input": {first_in: prev_ref},
            "output": {first_out: local_alias},
        })
        prev_ref = f"steps.{step_id}.{first_out}" if not is_last else prev_ref

    doc = {
        "id": suggested_id,
        "version": "0.1.0",
        "name": name,
        "description": f"TODO: {intent[:120]}",
        "inputs": {
            "input_text": {
                "type": "string",
                "required": True,
                "description": "Primary input for the workflow.",
            }
        },
        "outputs": {
            "result": {
                "type": "string",
                "description": "Workflow result.",
            }
        },
        "steps": steps,
        "metadata": {
            "channel": target_channel,
            "status": "draft",
            "tags": [],
        },
    }
    return yaml.dump(doc, default_flow_style=False, allow_unicode=True, sort_keys=False)


# ---------------------------------------------------------------------------
# LLM mode
# ---------------------------------------------------------------------------

_SKILL_SCHEMA_EXAMPLE = """\
id: domain.slug-name          # required, format: domain.slug
version: 0.1.0                # required, semver
name: Human Readable Name     # required
description: >                # required
  One or two sentence description of what the skill does.

inputs:
  field_name:                 # snake_case
    type: string              # string | integer | number | boolean | array | object
    required: true
    description: What this input contains.

outputs:
  result_field:
    type: string
    description: What this output contains.

steps:
  - id: step_one              # unique, snake_case
    uses: capability.id       # must be a VALID capability id from the list below
    input:
      capability_input_field: inputs.field_name    # inputs.X = skill input
    output:
      capability_output_field: step_one_result     # local alias for this step's output

  - id: step_two
    uses: another.capability
    input:
      text: steps.step_one.step_one_result         # steps.STEP_ID.ALIAS = previous step output
    output:
      summary: outputs.result_field                # outputs.X = writes to skill output directly

metadata:
  channel: local              # local | experimental | community
  status: draft
  tags: []
"""

_SYSTEM_PROMPT = """\
You are a skill YAML generator for the agent-skills framework.
Your job: given a natural-language intent, output EXACTLY ONE valid skill YAML document.

## Skill YAML schema and wiring rules

{schema_example}

## Available capabilities (use ONLY these ids in `uses:`)

{capability_list}

## Rules

1. Only use capability IDs from the list above — never invent new ones.
2. Wire outputs from one step as inputs to the next using `steps.STEP_ID.ALIAS`.
3. Map the final step output directly to `outputs.FIELD` using `outputs.fieldname`.
4. Choose the minimum set of capabilities that cover the intent (2–6 steps is typical).
5. Provide meaningful input/output field names, not just "text" everywhere.
6. Set `metadata.channel` to `{target_channel}`.
7. Output ONLY the YAML — no explanation, no markdown fences, no commentary.
"""

def _build_capability_list(capabilities: list[dict[str, Any]]) -> str:
    lines = []
    for cap in capabilities:
        cap_id = cap.get("id", "")
        desc = cap.get("description", "").split("\n")[0][:100]
        cap_inputs = list(cap.get("inputs", {}).keys())
        cap_outputs = list(cap.get("outputs", {}).keys())
        inp_str = ", ".join(cap_inputs) if cap_inputs else "—"
        out_str = ", ".join(cap_outputs) if cap_outputs else "—"
        lines.append(f"- {cap_id}: {desc} | inputs: {inp_str} | outputs: {out_str}")
    return "\n".join(lines)


def _call_openai(
    prompt: str,
    system: str,
    model: str,
    api_key: str,
) -> str:
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 1200,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"OpenAI API error {e.code}: {error_body[:300]}"
        ) from e

    return body["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Inline validator
# ---------------------------------------------------------------------------

def _validate_skill_yaml(raw: dict[str, Any], known_cap_ids: set[str]) -> list[str]:
    errors: list[str] = []

    for field in ("id", "version", "name", "description"):
        if not isinstance(raw.get(field), str) or not raw[field].strip():
            errors.append(f"Missing or empty required field: '{field}'")

    if not isinstance(raw.get("inputs"), dict):
        errors.append("'inputs' must be a mapping")
    if not isinstance(raw.get("outputs"), dict):
        errors.append("'outputs' must be a mapping")
    if not isinstance(raw.get("steps"), list) or not raw.get("steps"):
        errors.append("'steps' must be a non-empty list")
        return errors

    seen_step_ids: set[str] = set()
    for i, step in enumerate(raw["steps"]):
        sid = step.get("id")
        if not sid:
            errors.append(f"Step {i}: missing 'id'")
        elif sid in seen_step_ids:
            errors.append(f"Step {i}: duplicate step id '{sid}'")
        else:
            seen_step_ids.add(sid)

        uses = step.get("uses", "")
        if not uses:
            errors.append(f"Step '{sid}': missing 'uses'")
        elif known_cap_ids and not uses.startswith("skill:") and uses not in known_cap_ids:
            errors.append(f"Step '{sid}': unknown capability '{uses}'")

    return errors


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_skill_from_prompt(
    intent_description: str,
    registry_root: str | None = None,
    target_channel: str = "local",
    model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    """
    Generate a skill YAML from a natural-language intent description.

    Returns a dict with:
      skill_yaml:         str  — complete YAML text
      suggested_id:       str  — inferred skill id
      capabilities_used:  list — capability ids in the generated steps
      validation_errors:  list — schema violations (empty = valid)
    """
    reg_root = _find_registry_root(registry_root)
    capabilities = _load_capabilities(reg_root) if reg_root else []
    known_ids: set[str] = {c.get("id", "") for c in capabilities}

    suggested_id = _suggest_id(intent_description)
    api_key = os.environ.get("OPENAI_API_KEY", "")

    if api_key and capabilities:
        # --- LLM mode ---
        cap_list = _build_capability_list(capabilities)
        system = _SYSTEM_PROMPT.format(
            schema_example=_SKILL_SCHEMA_EXAMPLE,
            capability_list=cap_list,
            target_channel=target_channel,
        )
        raw_text = _call_openai(intent_description, system, model, api_key)

        # Strip markdown fences if present
        raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text.strip(), flags=re.MULTILINE)
        raw_text = re.sub(r"\n?```$", "", raw_text.strip(), flags=re.MULTILINE)
        skill_yaml = raw_text.strip() + "\n"

    else:
        # --- Template mode ---
        matched = _rank_capabilities(intent_description, capabilities)
        skill_yaml = _build_template_skill(
            intent_description, suggested_id, matched, target_channel
        )

    # Parse and validate
    try:
        parsed = yaml.safe_load(skill_yaml)
        if not isinstance(parsed, dict):
            return {
                "skill_yaml": skill_yaml,
                "suggested_id": suggested_id,
                "capabilities_used": [],
                "validation_errors": ["Generated content is not a YAML mapping."],
            }
        # Override suggested_id from what the LLM actually generated
        suggested_id = parsed.get("id", suggested_id)
    except yaml.YAMLError as exc:
        return {
            "skill_yaml": skill_yaml,
            "suggested_id": suggested_id,
            "capabilities_used": [],
            "validation_errors": [f"YAML parse error: {exc}"],
        }

    validation_errors = _validate_skill_yaml(parsed, known_ids)

    capabilities_used = []
    for step in parsed.get("steps", []):
        uses = step.get("uses", "")
        if uses and not uses.startswith("skill:") and uses not in capabilities_used:
            capabilities_used.append(uses)

    return {
        "skill_yaml": skill_yaml,
        "suggested_id": suggested_id,
        "capabilities_used": capabilities_used,
        "validation_errors": validation_errors,
    }
