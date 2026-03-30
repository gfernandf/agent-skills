"""
Skill: wizard — standalone utility.

Generate a skill YAML from a user goal + available capabilities,
calling OpenAI via raw HTTP (no `openai` package required).

Usage:
    python skills/wizard/skill.py "I want a skill that ..."

The main scaffold flow (cli.main scaffold --wizard) does NOT call
this script; it uses _call_openai() inside scaffold_service.py
directly.  This file exists as a standalone utility for manual use.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
import urllib.error
import yaml
from pathlib import Path


def discover_capabilities(
    *dirs: str,
) -> list[dict]:
    """Load capability YAMLs from one or more directories."""
    seen: dict[str, dict] = {}
    for d in dirs:
        p = Path(d)
        if not p.is_dir():
            continue
        for path in p.rglob("*.yaml"):
            try:
                with open(path, encoding="utf-8") as f:
                    doc = yaml.safe_load(f)
                if doc and isinstance(doc, dict) and "id" in doc:
                    seen.setdefault(doc["id"], {
                        "id": doc["id"],
                        "description": (doc.get("description") or "")[:120],
                    })
            except Exception:
                continue
    return list(seen.values())


def call_openai(prompt: str, system: str, api_key: str,
                model: str = "gpt-4o-mini") -> str:
    """Call OpenAI chat completions via urllib (no SDK needed)."""
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
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API error {e.code}: {err[:300]}") from e

    return body["choices"][0]["message"]["content"]


def propose_skill_yaml(user_goal: str, capabilities: list[dict],
                       api_key: str) -> str:
    """Ask the LLM to produce a skill YAML for *user_goal*."""
    cap_block = "\n".join(
        f"- {c['id']}: {c['description']}" for c in capabilities[:60]
    )
    system = (
        "You are a skill YAML generator for agent-skills. "
        "Reply with ONLY valid YAML — no markdown fences, no explanation. "
        "The YAML must have: id, version (0.1.0), name, description, "
        "inputs (mapping), outputs (mapping), steps (list). "
        "Each step has id, uses (a capability id), input (mapping), "
        "output (mapping)."
    )
    user = (
        f"Goal: {user_goal}\n\n"
        f"Available capabilities:\n{cap_block}\n\n"
        "Generate a skill.yaml that accomplishes the goal using the most "
        "relevant capabilities. Chain steps logically. "
        "Reply ONLY with the YAML."
    )
    raw = call_openai(user, system, api_key)
    # Strip accidental fences
    cleaned = re.sub(r"^```(?:yaml)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    # Sanity: must parse as dict
    doc = yaml.safe_load(cleaned)
    if not isinstance(doc, dict):
        raise ValueError(f"LLM returned non-mapping YAML ({type(doc).__name__})")
    return cleaned


if __name__ == "__main__":
    goal = sys.argv[1] if len(sys.argv) > 1 else input(
        "What should the new skill do?\n> "
    ).strip()
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("Error: OPENAI_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    caps = discover_capabilities(
        "skills/",
        "../agent-skill-registry/capabilities/",
    )
    print(f"[wizard] Discovered {len(caps)} capabilities.", file=sys.stderr)

    try:
        result = propose_skill_yaml(goal, caps, api_key)
    except Exception as exc:
        print(f"[wizard] Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(result)
