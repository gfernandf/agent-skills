"""
Scaffold service: generate skill YAML from a natural-language intent.

This module is the pythoncall backend for capability `agent.plan.create`.

Default behavior is **binding-first**:
- Ask `agent.plan.generate` through the runtime capability executor, so planning
  uses whatever bindings/services the user has configured.
- Build skill YAML using deterministic template synthesis.

Optional direct provider mode exists for experimentation via env var:
`AGENT_SKILLS_SCAFFOLDER_MODE=direct-openai`.

The output is always validated against the runtime skill schema constraints.
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


def _find_runtime_root(hint: str | None) -> Path:
    if hint:
        p = Path(hint)
        if p.is_dir():
            return p
    return Path(__file__).resolve().parent.parent


def _find_host_root(hint: str | None, runtime_root: Path) -> Path:
    if hint:
        p = Path(hint)
        if p.is_dir():
            return p
    return runtime_root


# ---------------------------------------------------------------------------
# ID / slug helpers
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "as",
    "is",
    "it",
    "its",
    "that",
    "this",
    "then",
    "when",
    "if",
    "so",
    "via",
    "into",
    "out",
    # Common intent verbs that shouldn't appear in skill IDs
    "i",
    "me",
    "my",
    "want",
    "need",
    "would",
    "like",
    "should",
    "could",
    "can",
    "will",
    "do",
    "does",
    "did",
    "get",
    "give",
    "given",
    "make",
    "create",
    "build",
    "have",
    "has",
    "be",
    "am",
    "are",
    "was",
    "were",
    "been",
    "being",
    "able",
    "also",
    "use",
    "using",
    "please",
    "just",
    "some",
    "workflow",
    "input",
    "output",
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
    preferred_capability_ids: list[str] | None = None,
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
        cap_domain = (
            cap_id.split(".")[0] if isinstance(cap_id, str) and "." in cap_id else ""
        )
        cap_words = set(
            re.findall(r"[a-z]+", (cap_id + " " + cap.get("description", "")).lower())
        )
        lexical_overlap = len(intent_words & cap_words)
        score = lexical_overlap

        domain_match = cap_domain in mentioned_domains
        if domain_match:
            score += 3

        # Penalize generic but unrelated capabilities.
        if lexical_overlap == 0 and not domain_match:
            score -= 4

        # Prefer capabilities whose primary input can be seeded from a text input.
        input_names = list((cap.get("inputs") or {}).keys())
        if input_names and (lexical_overlap > 0 or domain_match):
            first_in = input_names[0]
            if first_in in {"text", "content", "query", "input", "document", "prompt"}:
                score += 2

        if preferred_capability_ids and cap_id in preferred_capability_ids:
            score += 8

        return score

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
            if score <= 0 and len(selected) >= 2:
                break
            selected.append(cap)
            seen_ids.add(cap.get("id", ""))
            if len(selected) >= top_n:
                break

    return selected[:top_n] if selected else capabilities[:3]


def _infer_goal_capability_ids(intent: str) -> list[str]:
    txt = intent.lower()
    ordered_matches: list[tuple[tuple[str, ...], str]] = [
        (("extract", "entity"), "text.entity.extract"),
        (("extract", "entities"), "text.entity.extract"),
        (("named", "entity"), "text.entity.extract"),
        (("keyword",), "text.keyword.extract"),
        (("keywords",), "text.keyword.extract"),
        (("translate",), "text.content.translate"),
        (("translation",), "text.content.translate"),
        (("summarize",), "text.content.summarize"),
        (("summary",), "text.content.summarize"),
        (("detect", "language"), "text.language.detect"),
        (("identify", "language"), "text.language.detect"),
        (("sentiment",), "text.content.classify"),
        (("classify",), "text.content.classify"),
        (("classification",), "text.content.classify"),
        (("categorize",), "text.content.classify"),
        (("embed",), "text.content.embed"),
        (("embedding",), "text.content.embed"),
        (("extract", "text"), "text.content.extract"),
    ]

    goal_ids: list[str] = []
    for keywords, cap_id in ordered_matches:
        if all(keyword in txt for keyword in keywords) and cap_id not in goal_ids:
            goal_ids.append(cap_id)
    return goal_ids


# ---------------------------------------------------------------------------
# Template-mode generator
# ---------------------------------------------------------------------------


def _build_template_skill(
    intent: str,
    suggested_id: str,
    matched_caps: list[dict[str, Any]],
    target_channel: str,
    goal_capability_ids: list[str] | None = None,
) -> str:
    """Build a well-formed but stub skill YAML without an LLM."""
    parts = suggested_id.split(".", 1)
    slug = parts[1] if len(parts) > 1 else suggested_id
    name = slug.replace("-", " ").title()

    desired_output_type = _infer_desired_output_type(intent)
    selected_caps = _select_executable_template_caps(
        matched_caps,
        max_steps=4,
        desired_output_type=desired_output_type,
        goal_capability_ids=goal_capability_ids,
    )

    steps = []
    prev_ref = "inputs.text"
    last_output_type = desired_output_type
    for i, cap in enumerate(selected_caps):
        cap_id = cap.get("id", "unknown")
        step_id = f"{cap_id.replace('.', '_')}_step{i + 1}"
        is_last = i == len(selected_caps) - 1

        cap_in_fields = list(cap.get("inputs", {}).keys())
        first_in = cap_in_fields[0] if cap_in_fields else "text"
        next_first_input_type = None
        if not is_last:
            next_cap = selected_caps[i + 1]
            next_inputs = (
                next_cap.get("inputs")
                if isinstance(next_cap.get("inputs"), dict)
                else {}
            )
            next_in_name = list(next_inputs.keys())[0] if next_inputs else None
            if isinstance(next_in_name, str):
                next_first_input_type = _field_type(next_inputs.get(next_in_name))

        preferred_names = [
            "summary",
            "text",
            "content",
            "result",
            "label",
            "route",
            "findings",
        ]
        first_out, first_out_type = _choose_output_field(
            cap,
            preferred_type=(desired_output_type if is_last else next_first_input_type),
            preferred_names=preferred_names,
        )
        if is_last:
            last_output_type = first_out_type or desired_output_type

        var_alias = f"{step_id}_{first_out}".replace(".", "_")
        local_target = "outputs.result" if is_last else f"vars.{var_alias}"

        step_input = _build_step_input_mapping(cap, first_in, prev_ref, intent)

        steps.append(
            {
                "id": step_id,
                "uses": cap_id,
                "input": step_input,
                "output": {first_out: local_target},
            }
        )
        prev_ref = f"vars.{var_alias}" if not is_last else prev_ref

    doc = {
        "id": suggested_id,
        "version": "0.1.0",
        "name": name,
        "description": f"TODO: {intent[:120]}",
        "inputs": {
            "text": {
                "type": "string",
                "required": True,
                "description": "Primary input for the workflow.",
            }
        },
        "outputs": {
            "result": {
                "type": last_output_type,
                "description": f"Workflow result ({last_output_type}).",
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


def _required_input_fields(cap: dict[str, Any]) -> list[str]:
    required: list[str] = []
    inputs = cap.get("inputs") or {}
    if not isinstance(inputs, dict):
        return required
    for name, spec in inputs.items():
        if not isinstance(spec, dict):
            continue
        is_required = bool(spec.get("required", False))
        has_default = "default" in spec and spec.get("default") is not None
        if is_required and not has_default:
            required.append(name)
    return required


def _infer_language_defaults(intent_text: str) -> tuple[str | None, str | None]:
    txt = intent_text.lower()
    language_map = {
        "english": "en",
        "spanish": "es",
        "french": "fr",
        "german": "de",
        "italian": "it",
        "portuguese": "pt",
        "dutch": "nl",
    }

    source_language = None
    target_language = None
    for label, code in language_map.items():
        if f"to {label}" in txt or f"into {label}" in txt:
            target_language = code
        if f"from {label}" in txt:
            source_language = code

    return source_language, target_language


def _default_input_value(
    field_name: str, field_spec: Any, intent_text: str = ""
) -> Any:
    ftype = _field_type(field_spec) or "string"
    source_language, target_language = _infer_language_defaults(intent_text)

    if field_name == "labels" and ftype == "array":
        if "sentiment" in intent_text.lower():
            return ["positive", "neutral", "negative"]
        return ["positive", "neutral", "negative"]
    if field_name in {"target_language", "target_lang", "to_language"}:
        if target_language:
            return target_language
        return "en"
    if field_name in {"source_language", "source_lang", "from_language"}:
        if source_language:
            return source_language
        return "auto"
    if field_name in {"max_length", "limit", "top_k"} and ftype in {
        "integer",
        "number",
    }:
        return 120

    if ftype == "boolean":
        return False
    if ftype == "integer":
        return 0
    if ftype == "number":
        return 0
    if ftype == "array":
        return []
    if ftype == "object":
        return {}
    return "sample"


def _build_step_input_mapping(
    cap: dict[str, Any], first_in: str, prev_ref: str, intent_text: str
) -> dict[str, Any]:
    mapping: dict[str, Any] = {first_in: prev_ref}
    inputs = cap.get("inputs") or {}
    if not isinstance(inputs, dict):
        return mapping

    cap_id = str(cap.get("id", ""))

    for field_name in _required_input_fields(cap):
        if field_name in mapping:
            continue
        mapping[field_name] = _default_input_value(
            field_name, inputs.get(field_name), intent_text
        )

    # Some bindings require fields that are not marked as required in catalog specs.
    if (
        cap_id == "text.content.classify"
        and "labels" in inputs
        and "labels" not in mapping
    ):
        mapping["labels"] = _default_input_value(
            "labels", inputs.get("labels"), intent_text
        )
    if cap_id == "text.content.translate":
        if "source_language" in inputs and "source_language" not in mapping:
            mapping["source_language"] = _default_input_value(
                "source_language", inputs.get("source_language"), intent_text
            )
        if "target_language" in inputs and "target_language" not in mapping:
            mapping["target_language"] = _default_input_value(
                "target_language", inputs.get("target_language"), intent_text
            )

    return mapping


def _can_autofill_input(field_name: str) -> bool:
    return field_name in {
        "labels",
        "target_language",
        "target_lang",
        "to_language",
        "source_language",
        "source_lang",
        "from_language",
        "max_length",
        "limit",
        "top_k",
    }


def _is_template_seedable(cap: dict[str, Any]) -> bool:
    required_inputs = _required_input_fields(cap)
    if not required_inputs:
        return True
    primary_input = next(iter((cap.get("inputs") or {}).keys()), None)
    unresolved = [
        field
        for field in required_inputs
        if field != primary_input and not _can_autofill_input(field)
    ]
    return not unresolved


def _field_type(spec: Any) -> str | None:
    if isinstance(spec, dict):
        t = spec.get("type")
        if isinstance(t, str) and t:
            return t
    return None


def _infer_desired_output_type(intent: str) -> str:
    txt = intent.lower()
    boolean_hints = [
        "whether",
        "detect if",
        "check if",
        "is valid",
        "compliant",
        "true or false",
        "boolean",
        "contains pii",
    ]
    for hint in boolean_hints:
        if hint in txt:
            return "boolean"

    array_hints = ["list", "items", "entities", "keywords", "records"]
    for hint in array_hints:
        if hint in txt:
            return "array"

    return "string"


def _choose_output_field(
    cap: dict[str, Any],
    *,
    preferred_type: str | None,
    preferred_names: list[str],
) -> tuple[str, str]:
    outputs = cap.get("outputs")
    if not isinstance(outputs, dict) or not outputs:
        return "result", preferred_type or "string"

    # 1) name + type match
    for name in preferred_names:
        if name in outputs:
            t = _field_type(outputs.get(name)) or "string"
            if preferred_type is None or t == preferred_type:
                return name, t

    # 2) type match any field
    if preferred_type:
        for out_name, out_spec in outputs.items():
            t = _field_type(out_spec)
            if t == preferred_type:
                return out_name, t

    # 3) preferred name regardless of type
    for name in preferred_names:
        if name in outputs:
            t = _field_type(outputs.get(name)) or "string"
            return name, t

    # 4) first available
    first_name = next(iter(outputs))
    first_type = _field_type(outputs.get(first_name)) or "string"
    return first_name, first_type


def _primary_input_type(cap: dict[str, Any]) -> str | None:
    inputs = cap.get("inputs")
    if not isinstance(inputs, dict) or not inputs:
        return None
    first_name = next(iter(inputs))
    return _field_type(inputs.get(first_name)) or "string"


def _cap_output_types(cap: dict[str, Any]) -> set[str]:
    outputs = cap.get("outputs")
    if not isinstance(outputs, dict):
        return set()
    return {_field_type(spec) or "string" for spec in outputs.values()}


def _types_compatible(output_type: str | None, input_type: str | None) -> bool:
    if output_type is None or input_type is None:
        return True
    return output_type == input_type


def _select_executable_template_caps(
    caps: list[dict[str, Any]],
    max_steps: int,
    desired_output_type: str,
    goal_capability_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Select capabilities likely to execute in a single-input chain.

    Heuristic:
    - Keep capabilities with at most one required input without default.
    - Prefer capabilities whose input names are text-chain-friendly.
    """
    preferred_input_names = {
        "text",
        "content",
        "query",
        "input",
        "document",
        "prompt",
        "objective",
        "goal",
        "message",
    }

    viable: list[tuple[int, dict[str, Any]]] = []
    for cap in caps:
        if not _is_template_seedable(cap):
            continue

        inputs = cap.get("inputs") or {}
        input_names = list(inputs.keys()) if isinstance(inputs, dict) else []
        score = 0
        if input_names:
            if input_names[0] in preferred_input_names:
                score += 3
            if any(n in preferred_input_names for n in input_names):
                score += 1

        # Penalize operations that often require structured/non-text context.
        cap_id = str(cap.get("id", ""))
        if cap_id.startswith("doc.") or cap_id.startswith("table."):
            score -= 2

        output_specs = cap.get("outputs")
        if isinstance(output_specs, dict):
            output_types = {
                _field_type(v) for v in output_specs.values() if _field_type(v)
            }
            if desired_output_type in output_types:
                score += 3

        viable.append((score, cap))

    viable.sort(key=lambda x: -x[0])
    sorted_caps = [cap for _, cap in viable]

    direct_goal_caps = {
        "text.content.translate",
        "text.content.summarize",
        "text.content.classify",
        "text.entity.extract",
        "text.keyword.extract",
        "text.language.detect",
        "text.content.embed",
        "text.content.extract",
    }
    if goal_capability_ids:
        for goal_id in goal_capability_ids:
            if goal_id not in direct_goal_caps:
                continue
            for cap in sorted_caps:
                if cap.get("id") != goal_id:
                    continue
                input_type = _primary_input_type(cap)
                output_types = _cap_output_types(cap)
                if _types_compatible("string", input_type) and (
                    desired_output_type in output_types or not output_types
                ):
                    return [cap]

    terminal_cap: dict[str, Any] | None = None
    for cap in sorted_caps:
        types = _cap_output_types(cap)
        if desired_output_type in types:
            terminal_cap = cap
            break

    if terminal_cap is None and sorted_caps:
        terminal_cap = sorted_caps[0]

    selected: list[dict[str, Any]] = []
    current_type = "string"
    remaining = [cap for cap in sorted_caps if cap is not terminal_cap]

    while remaining and len(selected) < max_steps - 1:
        next_index: int | None = None
        for idx, cap in enumerate(remaining):
            input_type = _primary_input_type(cap)
            if _types_compatible(current_type, input_type):
                next_index = idx
                break
        if next_index is None:
            break

        cap = remaining.pop(next_index)
        selected.append(cap)
        cap_output_types = _cap_output_types(cap)
        if current_type in cap_output_types:
            current_type = current_type
        elif len(cap_output_types) == 1:
            current_type = next(iter(cap_output_types))

    if terminal_cap is not None:
        terminal_input_type = _primary_input_type(terminal_cap)
        if _types_compatible(current_type, terminal_input_type):
            selected.append(terminal_cap)
        elif not selected:
            selected.append(terminal_cap)

    if selected:
        return selected

    # Fallback: keep at least one capability to avoid empty skill generation.
    return caps[:1] if caps else []


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
            capability_output_field: vars.step_one_result  # vars.X for intermediate outputs

  - id: step_two
    uses: another.capability
    input:
            text: vars.step_one_result                    # vars.X = previous step output
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
2. Wire outputs from one step as inputs to the next using `vars.<name>`.
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


def _fix_llm_refs(yaml_text: str) -> str:
    """Post-process LLM-generated YAML to normalise ref syntax.

    Common LLM mistakes and their fixes:
      ${inputs.X}           → inputs.X
      ${steps.A.output.B}   → vars.A_B
      ${outputs.X}          → outputs.X
      ${output.X}           → outputs.X
      {{X}}                 → inputs.X   (Jinja-style)
    """
    import re as _re

    # ${inputs.X} → inputs.X
    yaml_text = _re.sub(r"\$\{inputs\.([^}]+)\}", r"inputs.\1", yaml_text)
    # ${outputs.X} and ${output.X} → outputs.X
    yaml_text = _re.sub(r"\$\{outputs?\.([^}]+)\}", r"outputs.\1", yaml_text)
    # ${steps.STEP_ID.output.FIELD} → vars.STEP_ID_FIELD
    yaml_text = _re.sub(
        r"\$\{steps\.([a-z_][a-z0-9_]*)\.outputs?\.([^}]+)\}",
        lambda m: f"vars.{m.group(1)}_{m.group(2)}",
        yaml_text,
    )
    # {{var_name}} → inputs.var_name
    yaml_text = _re.sub(r"\{\{(\w+)\}\}", r"inputs.\1", yaml_text)

    return yaml_text


def _call_openai(
    prompt: str,
    system: str,
    model: str,
    api_key: str,
) -> str:
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 1200,
        }
    ).encode("utf-8")

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
        raise RuntimeError(f"OpenAI API error {e.code}: {error_body[:300]}") from e

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
        elif (
            known_cap_ids
            and not uses.startswith("skill:")
            and uses not in known_cap_ids
        ):
            errors.append(f"Step '{sid}': unknown capability '{uses}'")

        output_mapping = step.get("output", {})
        if not isinstance(output_mapping, dict):
            errors.append(f"Step '{sid}': output mapping must be an object")
        else:
            for out_field, target in output_mapping.items():
                if not isinstance(target, str) or "." not in target:
                    errors.append(
                        f"Step '{sid}': invalid output target for '{out_field}' -> {target}"
                    )
                    continue
                namespace = target.split(".", 1)[0]
                if namespace not in {"vars", "outputs"}:
                    errors.append(
                        f"Step '{sid}': unsupported output namespace '{namespace}' (use vars.* or outputs.*)"
                    )

        input_mapping = step.get("input", {})
        if isinstance(input_mapping, dict):
            for in_field, ref in input_mapping.items():
                if isinstance(ref, str) and "." in ref:
                    ns = ref.split(".", 1)[0]
                    if ns not in {"inputs", "vars", "outputs"}:
                        errors.append(
                            f"Step '{sid}': unsupported input ref namespace '{ns}' for '{in_field}'"
                        )

    return errors


def _extract_capability_hints_from_plan(
    plan: Any,
    known_cap_ids: set[str],
) -> tuple[list[str], str]:
    hints: list[str] = []

    if isinstance(plan, dict):
        suggested = plan.get("suggested_capabilities")
        if isinstance(suggested, list):
            for item in suggested:
                if (
                    isinstance(item, str)
                    and item in known_cap_ids
                    and item not in hints
                ):
                    hints.append(item)

    text = json.dumps(plan, ensure_ascii=False) if plan is not None else ""
    for match in re.findall(r"\b[a-z]+\.[a-z][a-z0-9_.-]*\b", text):
        if match in known_cap_ids and match not in hints:
            hints.append(match)

    return hints, text


def _generate_plan_via_bindings(
    *,
    intent_description: str,
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    planning_capability_id: str,
    required_conformance_profile: str | None,
) -> tuple[Any | None, str | None]:
    try:
        from customer_facing.neutral_api import NeutralRuntimeAPI

        api = NeutralRuntimeAPI(
            registry_root=registry_root,
            runtime_root=runtime_root,
            host_root=host_root,
        )

        result = api.execute_capability(
            planning_capability_id,
            {"objective": intent_description},
            required_conformance_profile=required_conformance_profile,
        )
        outputs = result.get("outputs", {}) if isinstance(result, dict) else {}
        if isinstance(outputs, dict):
            return outputs.get("plan"), "binding-capability"
    except Exception:
        return None, None

    return None, None


def _build_probe_payload(cap: dict[str, Any], intent_text: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    inputs = cap.get("inputs")
    if not isinstance(inputs, dict):
        return payload

    text_like = {
        "text",
        "content",
        "query",
        "input",
        "document",
        "prompt",
        "objective",
        "goal",
        "message",
    }
    for field_name, field_spec in inputs.items():
        ftype = _field_type(field_spec) or "string"
        if field_name in text_like:
            payload[field_name] = intent_text
        elif ftype == "boolean":
            payload[field_name] = False
        elif ftype == "integer":
            payload[field_name] = 0
        elif ftype == "number":
            payload[field_name] = 0
        elif ftype == "array":
            payload[field_name] = []
        elif ftype == "object":
            payload[field_name] = {}
        else:
            payload[field_name] = "sample"

    return payload


def _filter_caps_by_runtime_probe(
    caps: list[dict[str, Any]],
    *,
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    intent_text: str,
    required_conformance_profile: str | None,
) -> list[dict[str, Any]]:
    """
    Keep capabilities that appear executable in the current runtime configuration.

    To avoid side effects in scaffolding, only probes capabilities whose metadata
    says `properties.side_effects == false`.
    """
    try:
        from customer_facing.neutral_api import NeutralRuntimeAPI

        api = NeutralRuntimeAPI(
            registry_root=registry_root,
            runtime_root=runtime_root,
            host_root=host_root,
        )
    except Exception:
        return caps

    kept: list[dict[str, Any]] = []
    for cap in caps:
        cap_id = str(cap.get("id", ""))
        if not cap_id:
            continue

        props = cap.get("properties") if isinstance(cap.get("properties"), dict) else {}
        side_effects = (
            bool(props.get("side_effects", False)) if isinstance(props, dict) else False
        )
        if side_effects:
            continue

        probe_payload = _build_probe_payload(cap, intent_text)
        try:
            api.execute_capability(
                cap_id,
                probe_payload,
                required_conformance_profile=required_conformance_profile,
            )
            kept.append(cap)
        except Exception:
            continue

    return kept if kept else caps


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_skill_from_prompt(
    intent_description: str,
    registry_root: str | None = None,
    target_channel: str = "local",
    model: str = "gpt-4o-mini",
    runtime_root: str | None = None,
    host_root: str | None = None,
    planning_capability_id: str = "agent.plan.generate",
    required_conformance_profile: str | None = None,
    wizard_capability_ids: list[str] | None = None,
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
    rt_root = _find_runtime_root(runtime_root)
    hs_root = _find_host_root(host_root, rt_root)

    suggested_id = _suggest_id(intent_description)
    api_key = os.environ.get("OPENAI_API_KEY", "")
    scaffolder_mode = (
        os.environ.get("AGENT_SKILLS_SCAFFOLDER_MODE", "binding-first").strip().lower()
    )
    goal_capability_ids = _infer_goal_capability_ids(intent_description)

    # --- LLM-driven wizard: call OpenAI directly via _call_openai ---
    if api_key:
        import re as _re
        import yaml as _yaml

        # 1) Semantic capability filtering: score by keyword overlap with intent
        _intent_tokens = set(
            _re.findall(r"[a-z]{3,}", intent_description.lower())
        )
        _scored: list[tuple[int, dict[str, Any]]] = []
        for _c in capabilities:
            _cid = _c.get("id", "")
            _cdesc = (_c.get("description") or "").lower()
            _cid_tokens = set(_re.findall(r"[a-z]{3,}", _cid.replace(".", " ")))
            _cdesc_tokens = set(_re.findall(r"[a-z]{3,}", _cdesc))
            _pool = _cid_tokens | _cdesc_tokens
            _overlap = len(_intent_tokens & _pool)
            _scored.append((_overlap, _c))
        _scored.sort(key=lambda x: x[0], reverse=True)
        _top_caps = [c for _, c in _scored[:60]]

        # 2) Build rich capability summary (id + description + inputs/outputs)
        cap_list_text = _build_capability_list(_top_caps)

        # 3) Use the production schema example and system prompt
        system_msg = _SYSTEM_PROMPT.format(
            schema_example=_SKILL_SCHEMA_EXAMPLE,
            capability_list=cap_list_text,
            target_channel=target_channel,
        )
        user_msg = (
            f"Goal: {intent_description}\n\n"
            "Generate a skill.yaml that accomplishes the goal using ONLY "
            "capability ids from the system prompt. Chain steps logically.\n"
            "Reply ONLY with the YAML content, nothing else."
        )

        try:
            raw_llm = _call_openai(
                prompt=user_msg,
                system=system_msg,
                model=model,
                api_key=api_key,
            )
            # Strip markdown fences if the LLM wraps them anyway
            cleaned = _re.sub(r"^```(?:yaml)?\s*", "", raw_llm.strip())
            cleaned = _re.sub(r"\s*```$", "", cleaned).strip()

            # 4) Post-process: fix common LLM ref syntax errors
            cleaned = _fix_llm_refs(cleaned)

            # Parse and validate
            doc = _yaml.safe_load(cleaned)
            if not isinstance(doc, dict):
                raise ValueError(
                    f"LLM returned non-mapping YAML (got {type(doc).__name__})"
                )

            used_caps: list[str] = []
            if isinstance(doc.get("steps"), list):
                used_caps = [
                    s.get("uses") for s in doc["steps"] if s.get("uses")
                ]
            llm_id = doc.get("id", suggested_id)

            # Re-serialize after post-processing to ensure clean output
            cleaned = _yaml.dump(doc, default_flow_style=False, sort_keys=False).strip()

            # Validate against schema
            validation_errors = _validate_skill_yaml(doc, known_ids)

            return {
                "skill_yaml": cleaned,
                "suggested_id": llm_id,
                "capabilities_used": used_caps,
                "validation_errors": validation_errors,
                "planning_source": "wizard-llm",
                "planning_capability_id": "wizard.llm",
                "scaffolder_mode": "llm-wizard",
            }
        except Exception as exc:
            # Fallback: return error as valid YAML so file is never empty
            fallback_yaml = (
                f"id: {suggested_id}\n"
                f"version: 0.1.0\n"
                f"name: '{intent_description[:60]}'\n"
                f"description: 'Auto-generated (LLM error — edit manually)'\n"
                f"# LLM_ERROR: {str(exc)[:200]}\n"
                f"inputs:\n  text:\n    type: string\n    required: true\n"
                f"outputs:\n  result:\n    type: string\n"
                f"steps: []\n"
            )
            return {
                "skill_yaml": fallback_yaml,
                "suggested_id": suggested_id,
                "capabilities_used": [],
                "validation_errors": [f"LLM wizard error: {exc}"],
                "planning_source": "wizard-llm",
                "planning_capability_id": "wizard.llm",
                "scaffolder_mode": "llm-wizard",
            }
    # --- END LLM wizard ---

    plan_obj, plan_source = (None, None)
    preferred_capability_ids: list[str] = []
    planning_text = ""

    if reg_root is not None:
        plan_obj, plan_source = _generate_plan_via_bindings(
            intent_description=intent_description,
            registry_root=reg_root,
            runtime_root=rt_root,
            host_root=hs_root,
            planning_capability_id=planning_capability_id,
            required_conformance_profile=required_conformance_profile,
        )

    if plan_obj is not None:
        preferred_capability_ids, planning_text = _extract_capability_hints_from_plan(
            plan_obj, known_ids
        )

    # Wizard selections take highest priority
    if wizard_capability_ids:
        for wc in reversed(wizard_capability_ids):
            if wc in known_ids and wc not in preferred_capability_ids:
                preferred_capability_ids.insert(0, wc)

    for goal_capability_id in reversed(goal_capability_ids):
        if (
            goal_capability_id in known_ids
            and goal_capability_id not in preferred_capability_ids
        ):
            preferred_capability_ids.insert(0, goal_capability_id)

    if scaffolder_mode == "direct-openai" and api_key and capabilities:
        # --- LLM mode ---
        cap_list = _build_capability_list(capabilities)
        system = _SYSTEM_PROMPT.format(
            schema_example=_SKILL_SCHEMA_EXAMPLE,
            capability_list=cap_list,
            target_channel=target_channel,
        )
        llm_prompt = intent_description
        if planning_text:
            llm_prompt = (
                f"{intent_description}\n\n"
                f"Planning context from {planning_capability_id}:\n{planning_text}"
            )
        raw_text = _call_openai(llm_prompt, system, model, api_key)

        # Strip markdown fences if present
        raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text.strip(), flags=re.MULTILINE)
        raw_text = re.sub(r"\n?```$", "", raw_text.strip(), flags=re.MULTILINE)
        skill_yaml = raw_text.strip() + "\n"

    else:
        # --- Binding-first template mode ---
        ranking_intent = intent_description
        if planning_text:
            ranking_intent = f"{intent_description} {planning_text}"
        matched = _rank_capabilities(
            ranking_intent,
            capabilities,
            preferred_capability_ids=preferred_capability_ids,
        )
        if reg_root is not None:
            matched = _filter_caps_by_runtime_probe(
                matched,
                registry_root=reg_root,
                runtime_root=rt_root,
                host_root=hs_root,
                intent_text=intent_description,
                required_conformance_profile=required_conformance_profile,
            )
        skill_yaml = _build_template_skill(
            intent_description,
            suggested_id,
            matched,
            target_channel,
            goal_capability_ids=goal_capability_ids,
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
        "planning_source": plan_source,
        "planning_capability_id": planning_capability_id,
        "scaffolder_mode": scaffolder_mode,
    }
