#!/usr/bin/env python3
"""Rename 24 two-segment capability IDs to three-segment domain.noun.verb format.

Usage:
    python rename_capabilities.py --dry-run     # Preview all changes
    python rename_capabilities.py --execute      # Apply all changes
    python rename_capabilities.py --verify       # Verify no old IDs remain
"""

import os
import re
import sys
from pathlib import Path
from collections import defaultdict

# ─── Rename mapping ──────────────────────────────────────────────

RENAME_MAP = {
    "agent.delegate": "agent.task.delegate",
    "agent.route": "agent.input.route",
    "analysis.split": "analysis.problem.split",
    "audio.transcribe": "audio.speech.transcribe",
    "code.execute": "code.snippet.execute",
    "code.format": "code.source.format",
    "doc.chunk": "doc.content.chunk",
    "email.read": "email.inbox.read",
    "email.send": "email.message.send",
    "fs.read": "fs.file.read",
    "image.classify": "image.content.classify",
    "memory.retrieve": "memory.entry.retrieve",
    "memory.store": "memory.entry.store",
    "message.send": "message.notification.send",
    "pdf.read": "pdf.document.read",
    "table.filter": "table.row.filter",
    "text.classify": "text.content.classify",
    "text.embed": "text.content.embed",
    "text.extract": "text.content.extract",
    "text.merge": "text.content.merge",
    "text.summarize": "text.content.summarize",
    "text.template": "text.content.template",
    "text.translate": "text.content.translate",
    "web.fetch": "web.page.fetch",
}

# ─── Paths ────────────────────────────────────────────────────────

REGISTRY = Path(r"c:\Users\Usuario\agent-skill-registry")
AGENT_SKILLS = Path(r"c:\Users\Usuario\agent-skills")

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "catalog"}
TEXT_EXTENSIONS = {".yaml", ".yml", ".json", ".py", ".md", ".txt"}


# ─── Pattern construction ─────────────────────────────────────────


def build_pattern():
    """Build a regex matching any old capability ID as a whole token.

    Boundary rules:
    - NOT preceded by [a-zA-Z0-9_]  (avoids matching inside longer identifiers)
    - NOT followed by [a-zA-Z0-9_-] (avoids matching skill names like text.summarize-summary)

    Dots CAN follow (to handle text.summarize.openapi.mock → text.content.summarize.openapi.mock)
    and CAN precede (to handle service.text.summarize → service.text.content.summarize).
    """
    sorted_ids = sorted(RENAME_MAP.keys(), key=len, reverse=True)
    escaped = [re.escape(cid) for cid in sorted_ids]
    pattern = r"(?<![a-zA-Z0-9_])(" + "|".join(escaped) + r")(?![a-zA-Z0-9_\-])"
    return re.compile(pattern)


# ─── Phase 1: Text content replacements ──────────────────────────


def collect_text_files():
    """Collect all text files from both repos, excluding skip dirs and catalog."""
    files = []
    for root_dir in [REGISTRY, AGENT_SKILLS]:
        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fname in filenames:
                fpath = Path(dirpath) / fname
                if fpath.suffix.lower() in TEXT_EXTENSIONS:
                    files.append(fpath)
    return files


def replace_text_in_files(pattern, dry_run=True):
    """Scan all text files and apply capability ID replacements."""
    files = collect_text_files()
    changes = []

    for fpath in files:
        # Skip this script itself
        if fpath.name == "rename_capabilities.py":
            continue

        try:
            content = fpath.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = fpath.read_text(encoding="utf-8-sig")
            except Exception:
                continue
        except Exception:
            continue

        matches = list(pattern.finditer(content))
        if not matches:
            continue

        new_content = pattern.sub(lambda m: RENAME_MAP[m.group(1)], content)

        # Gather details per old_id
        id_counts = defaultdict(int)
        for m in matches:
            id_counts[m.group(1)] += 1

        changes.append(
            {
                "path": fpath,
                "replacements": len(matches),
                "detail": dict(id_counts),
            }
        )

        if not dry_run:
            fpath.write_text(new_content, encoding="utf-8")

    return changes


# ─── Phase 2: Rename capability YAML files ───────────────────────


def rename_capability_yamls(dry_run=True):
    """Rename capabilities/{old_id}.yaml → capabilities/{new_id}.yaml in registry."""
    renames = []
    cap_dir = REGISTRY / "capabilities"

    for old_id, new_id in RENAME_MAP.items():
        old_path = cap_dir / f"{old_id}.yaml"
        new_path = cap_dir / f"{new_id}.yaml"

        if old_path.exists() and not new_path.exists():
            renames.append((old_path, new_path))
            if not dry_run:
                old_path.rename(new_path)
        elif not old_path.exists() and new_path.exists():
            pass  # Already renamed
        elif old_path.exists() and new_path.exists():
            print(f"  WARNING: Both {old_path.name} and {new_path.name} exist!")

    return renames


# ─── Phase 3: Rename binding directories ─────────────────────────


def rename_binding_dirs(dry_run=True):
    """Rename bindings/official/{old_id}/ → bindings/official/{new_id}/ in agent-skills."""
    renames = []
    bind_dir = AGENT_SKILLS / "bindings" / "official"

    for old_id, new_id in RENAME_MAP.items():
        old_path = bind_dir / old_id
        new_path = bind_dir / new_id

        if old_path.is_dir() and not new_path.exists():
            renames.append((old_path, new_path))
            if not dry_run:
                old_path.rename(new_path)
        elif not old_path.exists() and new_path.is_dir():
            pass  # Already renamed
        elif old_path.is_dir() and new_path.exists():
            print(f"  WARNING: Both {old_path.name}/ and {new_path.name}/ exist!")

    return renames


# ─── Phase 4: Rename OpenAPI scenario files ──────────────────────


def rename_scenario_files(dry_run=True):
    """Rename tooling/openapi_scenarios/{old_id}.mock.json files."""
    renames = []
    scenario_dir = AGENT_SKILLS / "tooling" / "openapi_scenarios"

    if not scenario_dir.is_dir():
        return renames

    for old_id, new_id in RENAME_MAP.items():
        old_path = scenario_dir / f"{old_id}.mock.json"
        new_path = scenario_dir / f"{new_id}.mock.json"

        if old_path.exists() and not new_path.exists():
            renames.append((old_path, new_path))
            if not dry_run:
                old_path.rename(new_path)
        elif not old_path.exists() and new_path.exists():
            pass  # Already renamed

    return renames


# ─── Phase 5: Verification ───────────────────────────────────────


def verify_no_old_ids():
    """Verify that no old capability IDs remain in any text file."""
    pattern = build_pattern()
    new_ids = set(RENAME_MAP.values())
    files = collect_text_files()
    remaining = []

    for fpath in files:
        if fpath.name == "rename_capabilities.py":
            continue
        try:
            content = fpath.read_text(encoding="utf-8")
        except Exception:
            continue

        matches = list(pattern.finditer(content))
        if not matches:
            continue

        # Filter out false positives: old IDs that appear as substrings of new IDs
        real_ids = set()
        for m in matches:
            old_id = m.group(1)
            start, end = m.start(), m.end()
            # Check if this match is actually embedded in a longer new ID
            # Expand context window to check for new IDs containing this old one
            ctx_start = max(0, start - 30)
            ctx_end = min(len(content), end + 30)
            ctx = content[ctx_start:ctx_end]
            embedded = False
            for nid in new_ids:
                if old_id in nid and old_id != nid and nid in ctx:
                    embedded = True
                    break
            if not embedded:
                real_ids.add(old_id)

        if real_ids:
            remaining.append((fpath, real_ids))

    # Check for un-renamed files/dirs
    cap_dir = REGISTRY / "capabilities"
    bind_dir = AGENT_SKILLS / "bindings" / "official"
    scenario_dir = AGENT_SKILLS / "tooling" / "openapi_scenarios"

    for old_id in RENAME_MAP:
        if (cap_dir / f"{old_id}.yaml").exists():
            remaining.append((cap_dir / f"{old_id}.yaml", {"FILE_NOT_RENAMED"}))
        if (bind_dir / old_id).is_dir():
            remaining.append((bind_dir / old_id, {"DIR_NOT_RENAMED"}))
        if (scenario_dir / f"{old_id}.mock.json").exists():
            remaining.append(
                (scenario_dir / f"{old_id}.mock.json", {"FILE_NOT_RENAMED"})
            )

    return remaining


# ─── Main ─────────────────────────────────────────────────────────


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--dry-run"

    if mode == "--verify":
        print("=== VERIFICATION: Checking for remaining old capability IDs ===\n")
        remaining = verify_no_old_ids()
        if not remaining:
            print("  OK — No old two-segment capability IDs found anywhere.")
        else:
            print(f"  FOUND {len(remaining)} files still containing old IDs:\n")
            for fpath, ids in remaining:
                rel = fpath
                try:
                    rel = fpath.relative_to(REGISTRY)
                    prefix = "[registry]"
                except ValueError:
                    try:
                        rel = fpath.relative_to(AGENT_SKILLS)
                        prefix = "[skills] "
                    except ValueError:
                        prefix = ""
                print(f"    {prefix} {rel}  →  {', '.join(sorted(ids))}")
        return len(remaining) > 0

    dry_run = mode != "--execute"

    if dry_run:
        print("=" * 70)
        print("  DRY RUN — No changes will be written")
        print("  Run with --execute to apply all changes")
        print("=" * 70)
    else:
        print("=" * 70)
        print("  EXECUTING — Changes will be applied to both repos")
        print("=" * 70)

    print()
    pattern = build_pattern()

    # Phase 1: Text replacements
    print("─── Phase 1: Text content replacements ───\n")
    text_changes = replace_text_in_files(pattern, dry_run)
    for ch in text_changes:
        rel_path = ch["path"]
        try:
            rel_path = ch["path"].relative_to(REGISTRY)
            prefix = "[registry]"
        except ValueError:
            try:
                rel_path = ch["path"].relative_to(AGENT_SKILLS)
                prefix = "[skills] "
            except ValueError:
                prefix = ""
        detail_str = ", ".join(f"{k}×{v}" for k, v in sorted(ch["detail"].items()))
        print(
            f"  {prefix} {rel_path}  ({ch['replacements']} replacements: {detail_str})"
        )

    # Phase 2: Capability YAML file renames
    print(
        f"\n─── Phase 2: Capability YAML renames ({'' if dry_run else 'applied'}) ───\n"
    )
    cap_renames = rename_capability_yamls(dry_run)
    for old_p, new_p in cap_renames:
        print(f"  {old_p.name}  →  {new_p.name}")

    # Phase 3: Binding directory renames
    print(
        f"\n─── Phase 3: Binding directory renames ({'' if dry_run else 'applied'}) ───\n"
    )
    bind_renames = rename_binding_dirs(dry_run)
    for old_p, new_p in bind_renames:
        print(f"  {old_p.name}/  →  {new_p.name}/")

    # Phase 4: Scenario file renames
    print(
        f"\n─── Phase 4: Scenario file renames ({'' if dry_run else 'applied'}) ───\n"
    )
    scenario_renames = rename_scenario_files(dry_run)
    for old_p, new_p in scenario_renames:
        print(f"  {old_p.name}  →  {new_p.name}")
    if not scenario_renames:
        print("  (none)")

    # Summary
    total_replacements = sum(ch["replacements"] for ch in text_changes)
    print(f"\n{'=' * 70}")
    print("  SUMMARY")
    print(f"    Text files modified:        {len(text_changes)}")
    print(f"    Total text replacements:    {total_replacements}")
    print(f"    Capability YAMLs renamed:   {len(cap_renames)}")
    print(f"    Binding dirs renamed:       {len(bind_renames)}")
    print(f"    Scenario files renamed:     {len(scenario_renames)}")
    print(f"{'=' * 70}")

    if dry_run:
        print(
            "\n  To apply these changes, run:  python rename_capabilities.py --execute"
        )
    else:
        print("\n  All changes applied. Run --verify to confirm no old IDs remain.")


if __name__ == "__main__":
    sys.exit(main() or 0)
