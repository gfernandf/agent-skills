#!/usr/bin/env python3
"""
Batch skill scaffold tool.

Reads a JSON list of intents and generates skill skeletons for each one,
depositing them under skills/experimental/ in the registry (or a custom root).

Usage
-----
    python tooling/batch_scaffold.py intents.json
    python tooling/batch_scaffold.py intents.json --channel community --dry-run
    python tooling/batch_scaffold.py intents.json --out-root ./output_skills
    python tooling/batch_scaffold.py intents.json --report batch_report.json

Input format (intents.json)
---------------------------
    [
      {"intent": "Receive an email and classify its urgency"},
      {"intent": "Extract text from a PDF and summarize it", "channel": "community"},
      {"intent": "Route an incoming support ticket to the right team", "id": "task.ticket-route"}
    ]

Each entry supports:
  intent    (required) natural-language description
  channel   (optional, default: experimental) target channel
  id        (optional) override the auto-suggested id
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from official_services.scaffold_service import generate_skill_from_prompt


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="batch_scaffold",
        description="Generate skill YAML skeletons from a list of intents.",
    )
    parser.add_argument("intents_file", type=Path, help="JSON file with intent list.")
    parser.add_argument(
        "--channel",
        choices=["local", "experimental", "community"],
        default="experimental",
        help="Default target channel (overridden per-entry if set). Default: experimental.",
    )
    parser.add_argument(
        "--registry-root",
        type=Path,
        default=None,
        help="Path to agent-skill-registry root. Auto-detected if omitted.",
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        default=None,
        help=(
            "Root directory for generated skills. "
            "Defaults to <registry-root>/skills/<channel>/."
        ),
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="OpenAI model (used only when OPENAI_API_KEY is set).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and validate but do not write any files.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write a JSON report of results to this path.",
    )
    args = parser.parse_args()

    # Load intents
    try:
        entries: list[dict] = json.loads(
            args.intents_file.read_text(encoding="utf-8-sig")
        )
    except Exception as exc:
        print(
            f"[batch_scaffold] ERROR reading {args.intents_file}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    if not isinstance(entries, list):
        print(
            "[batch_scaffold] ERROR: intents file must be a JSON array.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    registry_root = args.registry_root or _find_registry_root()
    results = []
    written = 0
    skipped = 0
    errors_total = 0

    print(f"[batch_scaffold] Processing {len(entries)} intents")
    print(f"[batch_scaffold] Registry root: {registry_root}")
    print(f"[batch_scaffold] Dry run: {args.dry_run}")
    print()

    for i, entry in enumerate(entries):
        intent = entry.get("intent", "")
        if not intent:
            print(f"[{i + 1}/{len(entries)}] SKIP — missing 'intent' field")
            skipped += 1
            continue

        channel = entry.get("channel", args.channel)
        forced_id = entry.get("id")

        print(
            f"[{i + 1}/{len(entries)}] {intent[:70]}{'...' if len(intent) > 70 else ''}"
        )

        try:
            result = generate_skill_from_prompt(
                intent_description=intent,
                registry_root=str(registry_root) if registry_root else None,
                target_channel=channel,
                model=args.model,
            )
        except Exception as exc:
            print(f"         ERROR: {exc}")
            errors_total += 1
            results.append(
                {
                    "intent": intent,
                    "status": "error",
                    "error": str(exc),
                }
            )
            continue

        skill_id = forced_id or result["suggested_id"]
        validation_errors = result["validation_errors"]
        status_label = (
            "OK" if not validation_errors else f"WARN ({len(validation_errors)} issues)"
        )
        print(
            f"         id={skill_id}  caps={', '.join(result['capabilities_used']) or '—'}  {status_label}"
        )

        if validation_errors:
            for err in validation_errors:
                print(f"         ! {err}")

        if not args.dry_run:
            out_root = args.out_root
            if out_root is None and registry_root:
                out_root = registry_root / "skills" / channel
            elif out_root is None:
                out_root = Path.cwd() / "generated_skills"

            parts = skill_id.split(".", 1)
            domain = parts[0]
            slug = parts[1].replace(".", "-") if len(parts) >= 2 else "custom"
            target_dir = out_root / domain / slug
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / "skill.yaml"

            if target_file.exists():
                print(f"         OVERWRITE: {target_file}")

            # If forced id differs from suggested, patch the yaml
            skill_yaml = result["skill_yaml"]
            if forced_id and forced_id != result["suggested_id"]:
                skill_yaml = skill_yaml.replace(
                    f"id: {result['suggested_id']}", f"id: {forced_id}", 1
                )

            target_file.write_text(skill_yaml, encoding="utf-8")
            print(f"         -> {target_file}")
            written += 1

        results.append(
            {
                "intent": intent,
                "skill_id": skill_id,
                "capabilities_used": result["capabilities_used"],
                "validation_errors": validation_errors,
                "channel": channel,
                "status": "dry_run"
                if args.dry_run
                else ("warn" if validation_errors else "ok"),
            }
        )

    print()
    print(
        f"[batch_scaffold] Done: {written} written, {skipped} skipped, {errors_total} errors"
    )

    if args.report:
        args.report.write_text(
            json.dumps(
                {
                    "summary": {
                        "written": written,
                        "skipped": skipped,
                        "errors": errors_total,
                    },
                    "results": results,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"[batch_scaffold] Report written to {args.report}")


def _find_registry_root() -> Path | None:
    """Locate the registry root relative to this tool's location."""
    candidate = Path(__file__).resolve().parent.parent.parent / "agent-skill-registry"
    if candidate.is_dir():
        return candidate
    cwd_candidate = Path.cwd().parent / "agent-skill-registry"
    if cwd_candidate.is_dir():
        return cwd_candidate
    return None


if __name__ == "__main__":
    main()
