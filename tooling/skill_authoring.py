"""Skill authoring helpers — test runner, export/import, wiring checks, feedback.

Provides the operational logic behind the CLI authoring commands:
test, check-wiring, export, import, contribute, rate, report, discover --similar.
"""

from __future__ import annotations

import json
import shutil
import tarfile
import tempfile
import textwrap
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# M2 — Skill Test Runner
# ---------------------------------------------------------------------------

def generate_test_fixture(
    skill_doc: dict[str, Any],
) -> dict[str, Any]:
    """Generate a stub test_input.json from a skill's input schema."""
    inputs = skill_doc.get("inputs", {})
    fixture: dict[str, Any] = {}
    _TYPE_DEFAULTS = {
        "string": "example text",
        "integer": 1,
        "number": 1.0,
        "boolean": True,
        "array": [],
        "object": {},
    }
    for name, spec in inputs.items():
        if not isinstance(spec, dict):
            continue
        default = spec.get("default")
        if default is not None:
            fixture[name] = default
        else:
            field_type = spec.get("type", "string")
            fixture[name] = _TYPE_DEFAULTS.get(field_type, "")
    return fixture


def run_skill_test(
    *,
    engine: Any,
    skill_doc: dict[str, Any],
    inputs: dict[str, Any],
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Execute a skill and return a structured test report."""
    from runtime.models import ExecutionRequest
    import time

    skill_id = skill_doc["id"]
    expected_outputs = list(skill_doc.get("outputs", {}).keys())
    tid = trace_id or f"test-{skill_id.replace('.', '-')}-{int(time.time())}"

    req = ExecutionRequest(skill_id=skill_id, inputs=inputs, trace_id=tid, channel="test")

    start = time.perf_counter()
    try:
        result = engine.execute(req)
    except Exception as exc:
        return {
            "ok": False,
            "skill_id": skill_id,
            "status": "exception",
            "error": str(exc),
            "duration_ms": round((time.perf_counter() - start) * 1000),
            "trace_id": tid,
        }

    elapsed = round((time.perf_counter() - start) * 1000)
    output_keys = sorted(result.outputs.keys()) if result.outputs else []
    missing = [k for k in expected_outputs if k not in (result.outputs or {})]

    report: dict[str, Any] = {
        "ok": result.status == "completed" and not missing,
        "skill_id": skill_id,
        "status": result.status,
        "duration_ms": elapsed,
        "trace_id": tid,
        "output_keys": output_keys,
        "expected_outputs": expected_outputs,
        "missing_outputs": missing,
    }

    if result.status != "completed":
        report["error"] = getattr(result, "error", None)

    if result.outputs:
        report["outputs"] = result.outputs

    steps_done = len(result.state.step_results) if hasattr(result, "state") and result.state else 0
    report["steps_executed"] = steps_done

    return report


# ---------------------------------------------------------------------------
# M8 — Wiring Compatibility Check
# ---------------------------------------------------------------------------

def check_wiring(
    skill_doc: dict[str, Any],
    capabilities: dict[str, Any],
) -> list[dict[str, Any]]:
    """Check type compatibility between step outputs and downstream inputs."""
    issues: list[dict[str, Any]] = []
    steps = skill_doc.get("steps", [])
    if not isinstance(steps, list):
        return issues

    # Build a registry of what each step produces with types
    # vars.X -> type, outputs.X -> type
    var_types: dict[str, str] = {}

    # Skill inputs
    for name, spec in skill_doc.get("inputs", {}).items():
        if isinstance(spec, dict):
            var_types[f"inputs.{name}"] = spec.get("type", "string")

    for step in steps:
        if not isinstance(step, dict):
            continue
        step_id = step.get("id", "?")
        uses = step.get("uses", "")

        cap = capabilities.get(uses)
        cap_inputs = {}
        cap_outputs = {}
        if cap:
            cap_inputs = getattr(cap, "inputs", {}) or {}
            cap_outputs = getattr(cap, "outputs", {}) or {}

        # Check input wiring
        input_map = step.get("input") or step.get("input_mapping") or {}
        if isinstance(input_map, dict):
            for cap_field, source in input_map.items():
                if not isinstance(source, str):
                    continue
                # Check source exists in known vars
                if source.startswith("inputs.") or source.startswith("vars."):
                    source_type = var_types.get(source)
                    if source_type is None:
                        issues.append({
                            "level": "warning",
                            "step": step_id,
                            "message": f"Source '{source}' not produced by any prior step",
                        })
                    elif cap and cap_field in cap_inputs:
                        expected_type = cap_inputs[cap_field].get("type") if isinstance(cap_inputs[cap_field], dict) else None
                        if expected_type and source_type != expected_type:
                            issues.append({
                                "level": "warning",
                                "step": step_id,
                                "message": (
                                    f"Type mismatch: '{source}' is {source_type} "
                                    f"but {uses}.{cap_field} expects {expected_type}"
                                ),
                            })

        # Register outputs from this step
        output_map = step.get("output") or step.get("output_mapping") or {}
        if isinstance(output_map, dict):
            for cap_field, target in output_map.items():
                if not isinstance(target, str):
                    continue
                out_type = "string"
                if cap and cap_field in cap_outputs:
                    out_spec = cap_outputs[cap_field]
                    out_type = out_spec.get("type", "string") if isinstance(out_spec, dict) else "string"
                var_types[target] = out_type

    return issues


# ---------------------------------------------------------------------------
# M7 — Capability type filtering
# ---------------------------------------------------------------------------

def filter_capabilities_by_type(
    capabilities: dict[str, Any],
    input_type: str | None = None,
    output_type: str | None = None,
) -> list[Any]:
    """Filter capabilities by input/output field types."""
    results = []
    for cap_id, cap in sorted(capabilities.items()):
        cap_inputs = getattr(cap, "inputs", {}) or {}
        cap_outputs = getattr(cap, "outputs", {}) or {}

        if input_type:
            has_input = any(
                (isinstance(spec, dict) and spec.get("type") == input_type)
                for spec in cap_inputs.values()
            )
            if not has_input:
                continue

        if output_type:
            has_output = any(
                (isinstance(spec, dict) and spec.get("type") == output_type)
                for spec in cap_outputs.values()
            )
            if not has_output:
                continue

        results.append(cap)
    return results


# ---------------------------------------------------------------------------
# M6 — Mermaid DAG Generation
# ---------------------------------------------------------------------------

def generate_mermaid_dag(skill_doc: dict[str, Any]) -> str:
    """Generate a Mermaid flowchart from a skill's step DAG."""
    steps = skill_doc.get("steps", [])
    if not isinstance(steps, list) or not steps:
        return "graph LR\n  empty[No steps]"

    lines = ["graph LR"]
    step_ids = [s.get("id", f"step_{i}") for i, s in enumerate(steps)]

    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        sid = step.get("id", f"step_{i}")
        uses = step.get("uses", "?")
        label = f"{sid}\\n{uses}"
        lines.append(f'  {sid}["{label}"]')

    # Edges
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        sid = step.get("id", f"step_{i}")
        config = step.get("config") or {}
        deps = config.get("depends_on")
        if deps is not None:
            for dep in deps:
                if dep in step_ids:
                    lines.append(f"  {dep} --> {sid}")
        elif i > 0:
            lines.append(f"  {step_ids[i-1]} --> {sid}")

    # Mark inputs/outputs
    skill_name = skill_doc.get("name", skill_doc.get("id", "Skill"))
    input_fields = list(skill_doc.get("inputs", {}).keys())
    output_fields = list(skill_doc.get("outputs", {}).keys())

    if input_fields:
        lines.append(f'  IN(("{", ".join(input_fields)}"))')
        lines.append(f"  IN --> {step_ids[0]}")

    if output_fields:
        lines.append(f'  OUT(("{", ".join(output_fields)}"))')
        last_step = step_ids[-1]
        lines.append(f"  {last_step} --> OUT")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# M4 — Export / Import
# ---------------------------------------------------------------------------

def export_skill_bundle(
    skill_file: Path,
    output_path: Path | None = None,
) -> Path:
    """Create a .skill-bundle.tar.gz containing skill.yaml + test_input.json + README."""
    skill_dir = skill_file.parent
    skill_doc = yaml.safe_load(skill_file.read_text(encoding="utf-8"))
    skill_id = skill_doc.get("id", "unknown")

    if output_path is None:
        output_path = skill_dir / f"{skill_id.replace('.', '_')}.skill-bundle.tar.gz"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tarfile.open(str(output_path), "w:gz") as tar:
        # Add skill.yaml
        tar.add(str(skill_file), arcname="skill.yaml")

        # Add test_input.json if exists
        test_input = skill_dir / "test_input.json"
        if test_input.exists():
            tar.add(str(test_input), arcname="test_input.json")
        else:
            # Generate a stub
            fixture = generate_test_fixture(skill_doc)
            data = json.dumps(fixture, indent=2, ensure_ascii=False).encode("utf-8")
            import io
            import tarfile as _tf
            info = _tf.TarInfo(name="test_input.json")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        # Add README if exists
        readme = skill_dir / "README.md"
        if readme.exists():
            tar.add(str(readme), arcname="README.md")
        else:
            readme_content = textwrap.dedent(f"""\
                # {skill_doc.get('name', skill_id)}

                {skill_doc.get('description', 'No description.')}

                ## Inputs
                {_format_fields(skill_doc.get('inputs', {}))}

                ## Outputs
                {_format_fields(skill_doc.get('outputs', {}))}

                ## Quick Start

                ```bash
                agent-skills import {output_path.name}
                agent-skills test {skill_id}
                agent-skills run {skill_id} --input-file test_input.json
                ```
            """).encode("utf-8")
            import io
            import tarfile as _tf
            info = _tf.TarInfo(name="README.md")
            info.size = len(readme_content)
            tar.addfile(info, io.BytesIO(readme_content))

        # Add bundle manifest
        manifest = {
            "skill_id": skill_id,
            "version": skill_doc.get("version", "0.1.0"),
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "capabilities_used": [
                s.get("uses") for s in skill_doc.get("steps", [])
                if isinstance(s, dict) and s.get("uses")
            ],
        }
        manifest_data = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
        import io
        import tarfile as _tf
        info = _tf.TarInfo(name="bundle_manifest.json")
        info.size = len(manifest_data)
        tar.addfile(info, io.BytesIO(manifest_data))

    return output_path


def import_skill_bundle(
    source: str,
    local_skills_root: Path,
    capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Import a skill bundle from a path. Returns import report."""
    source_path = Path(source)
    if not source_path.exists():
        return {"ok": False, "error": f"Source not found: {source}"}

    with tarfile.open(str(source_path), "r:gz") as tar:
        # Safety: validate member names
        for member in tar.getmembers():
            if member.name.startswith("/") or ".." in member.name:
                return {"ok": False, "error": f"Unsafe path in bundle: {member.name}"}

        # Extract skill.yaml
        try:
            skill_f = tar.extractfile("skill.yaml")
            if skill_f is None:
                return {"ok": False, "error": "Bundle missing skill.yaml"}
            skill_doc = yaml.safe_load(skill_f.read())
        except (KeyError, Exception) as exc:
            return {"ok": False, "error": f"Cannot read skill.yaml: {exc}"}

        if not isinstance(skill_doc, dict) or "id" not in skill_doc:
            return {"ok": False, "error": "Invalid skill.yaml: missing 'id'"}

        skill_id = skill_doc["id"]
        if "." not in skill_id:
            return {"ok": False, "error": f"Invalid skill id '{skill_id}' (expected domain.slug)"}

        domain, slug = skill_id.split(".", 1)
        target_dir = local_skills_root / domain / slug
        target_dir.mkdir(parents=True, exist_ok=True)

        # Check capability compatibility
        missing_caps: list[str] = []
        if capabilities is not None:
            for step in skill_doc.get("steps", []):
                if not isinstance(step, dict):
                    continue
                uses = step.get("uses", "")
                if uses and not uses.startswith("skill:") and uses not in capabilities:
                    missing_caps.append(uses)

        # Extract all files
        extracted_files: list[str] = []
        for member in tar.getmembers():
            if member.isfile():
                content = tar.extractfile(member)
                if content:
                    target_file = target_dir / member.name
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    target_file.write_bytes(content.read())
                    extracted_files.append(member.name)

    report: dict[str, Any] = {
        "ok": True,
        "skill_id": skill_id,
        "imported_to": str(target_dir),
        "files": extracted_files,
    }
    if missing_caps:
        report["warnings"] = [
            f"Missing capability: {c} — skill may not be executable" for c in missing_caps
        ]

    return report


def _format_fields(fields: dict) -> str:
    if not fields:
        return "None"
    lines = []
    for name, spec in fields.items():
        if isinstance(spec, dict):
            ftype = spec.get("type", "?")
            desc = spec.get("description", "")
            req = " (required)" if spec.get("required") else ""
            lines.append(f"- **{name}** ({ftype}{req}): {desc}")
        else:
            lines.append(f"- **{name}**")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# M10 — Similar Skills Discovery
# ---------------------------------------------------------------------------

def find_similar_skills(
    skill_id: str,
    all_skills: dict[str, Any],
    capabilities: dict[str, Any] | None = None,
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """Find skills similar to the given one by capability overlap and keyword similarity."""
    if skill_id not in all_skills:
        return []

    target = all_skills[skill_id]
    target_caps = _extract_capability_ids(target)
    target_tags = _extract_tags(target)
    target_words = _extract_words(target)

    scored: list[tuple[float, str, dict]] = []
    for sid, skill in all_skills.items():
        if sid == skill_id:
            continue

        other_caps = _extract_capability_ids(skill)
        other_tags = _extract_tags(skill)
        other_words = _extract_words(skill)

        # Jaccard similarity on capabilities
        cap_union = target_caps | other_caps
        cap_inter = target_caps & other_caps
        cap_score = len(cap_inter) / len(cap_union) if cap_union else 0

        # Tag overlap
        tag_union = target_tags | other_tags
        tag_inter = target_tags & other_tags
        tag_score = len(tag_inter) / len(tag_union) if tag_union else 0

        # Word overlap (name + description)
        word_union = target_words | other_words
        word_inter = target_words & other_words
        word_score = len(word_inter) / len(word_union) if word_union else 0

        # Domain match bonus
        domain_bonus = 0.15 if sid.split(".")[0] == skill_id.split(".")[0] else 0

        total = (cap_score * 0.50) + (tag_score * 0.25) + (word_score * 0.10) + domain_bonus

        if total > 0.05:
            scored.append((total, sid, {
                "skill_id": sid,
                "similarity": round(total, 3),
                "shared_capabilities": sorted(cap_inter),
                "shared_tags": sorted(tag_inter),
                "name": _get_name(skill),
            }))

    scored.sort(key=lambda x: -x[0])
    return [item[2] for item in scored[:top_n]]


def _extract_capability_ids(skill: Any) -> set[str]:
    steps = []
    if isinstance(skill, dict):
        steps = skill.get("steps", [])
    else:
        steps = getattr(skill, "steps", [])
    return {
        s.get("uses") if isinstance(s, dict) else getattr(s, "uses", "")
        for s in steps
        if (isinstance(s, dict) and s.get("uses")) or (hasattr(s, "uses") and getattr(s, "uses", ""))
    }


def _extract_tags(skill: Any) -> set[str]:
    if isinstance(skill, dict):
        meta = skill.get("metadata", {})
    else:
        meta = getattr(skill, "metadata", {})
    if not isinstance(meta, dict):
        return set()
    tags = meta.get("tags", [])
    return set(tags) if isinstance(tags, list) else set()


def _get_name(skill: Any) -> str:
    if isinstance(skill, dict):
        return skill.get("name", "")
    return getattr(skill, "name", "")


def _extract_words(skill: Any) -> set[str]:
    if isinstance(skill, dict):
        text = f"{skill.get('name', '')} {skill.get('description', '')}"
    else:
        text = f"{getattr(skill, 'name', '')} {getattr(skill, 'description', '')}"
    return {w.lower() for w in text.split() if len(w) > 2}


# ---------------------------------------------------------------------------
# M11 — Skill Rating
# ---------------------------------------------------------------------------

def rate_skill(
    skill_id: str,
    score: int,
    comment: str | None,
    feedback_file: Path,
) -> dict[str, Any]:
    """Record a skill rating to the local feedback file."""
    if not 1 <= score <= 5:
        return {"ok": False, "error": "Score must be between 1 and 5"}

    feedback_file.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = {"ratings": []}
    if feedback_file.exists():
        try:
            existing = json.loads(feedback_file.read_text(encoding="utf-8"))
        except Exception:
            existing = {"ratings": []}

    if "ratings" not in existing:
        existing["ratings"] = []

    entry = {
        "skill_id": skill_id,
        "score": score,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if comment:
        entry["comment"] = comment

    existing["ratings"].append(entry)

    # Update aggregates
    skill_ratings = [r for r in existing["ratings"] if r.get("skill_id") == skill_id]
    avg = sum(r["score"] for r in skill_ratings) / len(skill_ratings)
    aggregates = existing.setdefault("aggregates", {})
    aggregates[skill_id] = {
        "rating_avg": round(avg, 2),
        "rating_count": len(skill_ratings),
    }

    feedback_file.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return {
        "ok": True,
        "skill_id": skill_id,
        "score": score,
        "new_average": round(avg, 2),
        "total_ratings": len(skill_ratings),
    }


# ---------------------------------------------------------------------------
# M12 — Skill Issue Report
# ---------------------------------------------------------------------------

def generate_issue_report(
    skill_id: str,
    issue_text: str,
    severity: str = "medium",
    execution_context: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Generate a GitHub issue body for a skill problem report."""
    title = f"[Skill Report] {skill_id}: {issue_text[:60]}"
    body_parts = [
        f"## Skill: `{skill_id}`\n",
        f"**Severity:** {severity}\n",
        f"**Reported:** {datetime.now(timezone.utc).isoformat()}\n",
        "## Description\n",
        f"{issue_text}\n",
    ]

    if execution_context:
        body_parts.append("## Execution Context\n")
        body_parts.append("```json\n")
        body_parts.append(json.dumps(execution_context, indent=2, ensure_ascii=False))
        body_parts.append("\n```\n")

    body_parts.extend([
        "## Expected Behavior\n",
        "<!-- Describe what you expected -->\n",
        "## Actual Behavior\n",
        "<!-- Describe what actually happened -->\n",
        "## Environment\n",
        "- agent-skills version: <!-- e.g. 0.1.0 -->\n",
        "- Python version: <!-- e.g. 3.14.3 -->\n",
    ])

    return {
        "title": title,
        "body": "\n".join(body_parts),
        "labels": f"bug,skill-report,severity-{severity}",
    }


# ---------------------------------------------------------------------------
# M14 — Auto-wiring Suggestions
# ---------------------------------------------------------------------------

def suggest_wiring(
    capabilities_sequence: list[str],
    capabilities: dict[str, Any],
    skill_inputs: dict[str, Any],
) -> list[dict[str, Any]]:
    """For a sequence of capabilities, suggest input/output wiring."""
    suggestions: list[dict[str, Any]] = []
    available_vars: dict[str, str] = {}  # var_name -> type

    # Register skill inputs
    for name, spec in skill_inputs.items():
        ftype = spec.get("type", "string") if isinstance(spec, dict) else "string"
        available_vars[f"inputs.{name}"] = ftype

    for i, cap_id in enumerate(capabilities_sequence):
        cap = capabilities.get(cap_id)
        if not cap:
            suggestions.append({"capability": cap_id, "error": "capability not found"})
            continue

        cap_inputs = getattr(cap, "inputs", {}) or {}
        cap_outputs = getattr(cap, "outputs", {}) or {}

        # Suggest input mapping
        input_suggestion: dict[str, str] = {}
        for field_name, field_spec in cap_inputs.items():
            expected_type = field_spec.get("type", "string") if isinstance(field_spec, dict) else "string"
            # Find best match from available vars
            best = _find_best_source(field_name, expected_type, available_vars)
            if best:
                input_suggestion[field_name] = best

        # Register outputs
        step_id = cap_id.split(".")[-1].replace("-", "_")
        if i > 0:
            step_id = f"step_{i}_{step_id}"
        output_suggestion: dict[str, str] = {}
        for field_name, field_spec in cap_outputs.items():
            out_type = field_spec.get("type", "string") if isinstance(field_spec, dict) else "string"
            var_name = f"vars.{step_id}_{field_name}"
            output_suggestion[field_name] = var_name
            available_vars[var_name] = out_type

        suggestions.append({
            "capability": cap_id,
            "suggested_input": input_suggestion,
            "suggested_output": output_suggestion,
        })

    return suggestions


def _find_best_source(
    field_name: str,
    expected_type: str,
    available_vars: dict[str, str],
) -> str | None:
    """Find the best matching source variable for a capability input field."""
    # Exact name match with correct type
    for var, vtype in available_vars.items():
        var_field = var.split(".")[-1]
        if var_field == field_name and vtype == expected_type:
            return var

    # Partial name match with correct type
    for var, vtype in available_vars.items():
        var_field = var.split(".")[-1]
        if vtype == expected_type and (field_name in var_field or var_field in field_name):
            return var

    # Type match only — prefer most recent (last registered)
    type_matches = [var for var, vtype in available_vars.items() if vtype == expected_type]
    if type_matches:
        return type_matches[-1]

    return None
