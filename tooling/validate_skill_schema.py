"""Validate skill YAML files against the published JSON Schemas.

Usage:
    python tooling/validate_skill_schema.py skills/my_skill.yaml
    python tooling/validate_skill_schema.py skills/       # all YAML files in directory

Requires no external dependencies — uses basic structural checks
against the JSON Schema definitions in docs/schemas/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "docs" / "schemas"


def _load_schema(name: str) -> dict[str, Any]:
    path = _SCHEMA_DIR / f"{name}.schema.json"
    if not path.exists():
        raise FileNotFoundError(f"Schema not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _check_required(data: dict, schema: dict, path: str = "") -> list[str]:
    """Check required fields and basic type constraints. Returns list of errors."""
    errors: list[str] = []
    required = schema.get("required", [])
    properties = schema.get("properties", {})

    for field in required:
        if field not in data:
            errors.append(f"{path}.{field}: required field missing")

    for field, prop_schema in properties.items():
        if field not in data:
            continue
        value = data[field]
        expected = prop_schema.get("type")
        if expected is None:
            continue

        # Handle union types like ["string", "null"]
        if isinstance(expected, list):
            type_ok = False
            for t in expected:
                if t == "null" and value is None:
                    type_ok = True
                elif t == "string" and isinstance(value, str):
                    type_ok = True
                elif (
                    t == "integer"
                    and isinstance(value, int)
                    and not isinstance(value, bool)
                ):
                    type_ok = True
                elif (
                    t == "number"
                    and isinstance(value, (int, float))
                    and not isinstance(value, bool)
                ):
                    type_ok = True
                elif t == "boolean" and isinstance(value, bool):
                    type_ok = True
                elif t == "object" and isinstance(value, dict):
                    type_ok = True
                elif t == "array" and isinstance(value, list):
                    type_ok = True
            if not type_ok:
                errors.append(
                    f"{path}.{field}: expected one of {expected}, got {type(value).__name__}"
                )
        else:
            _TYPE_MAP = {
                "string": str,
                "integer": int,
                "number": (int, float),
                "boolean": bool,
                "object": dict,
                "array": list,
            }
            py_type = _TYPE_MAP.get(expected)
            if py_type and not isinstance(value, py_type):
                errors.append(
                    f"{path}.{field}: expected {expected}, got {type(value).__name__}"
                )

        # Enum check
        if "enum" in prop_schema and value is not None:
            if value not in prop_schema["enum"]:
                errors.append(
                    f"{path}.{field}: value '{value}' not in {prop_schema['enum']}"
                )

    return errors


def validate_skill_yaml(filepath: Path) -> list[str]:
    """Validate a single skill YAML against SkillSpec schema."""
    errors: list[str] = []
    try:
        content = yaml.safe_load(filepath.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"YAML parse error: {e}"]

    if not isinstance(content, dict):
        return ["Root must be a YAML mapping"]

    schema = _load_schema("SkillSpec")
    errors.extend(_check_required(content, schema, path="skill"))

    # Validate steps
    steps = content.get("steps", [])
    if isinstance(steps, list):
        step_schema = _load_schema("StepSpec")
        for i, step in enumerate(steps):
            if isinstance(step, dict):
                errors.extend(
                    _check_required(step, step_schema, path=f"skill.steps[{i}]")
                )
            else:
                errors.append(
                    f"skill.steps[{i}]: expected object, got {type(step).__name__}"
                )

    # Validate inputs/outputs field specs
    field_schema = _load_schema("FieldSpec")
    for section in ("inputs", "outputs"):
        fields = content.get(section, {})
        if isinstance(fields, dict):
            for fname, fspec in fields.items():
                if isinstance(fspec, dict):
                    errors.extend(
                        _check_required(
                            fspec, field_schema, path=f"skill.{section}.{fname}"
                        )
                    )

    return errors


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python tooling/validate_skill_schema.py <path_or_dir>")
        sys.exit(1)

    target = Path(sys.argv[1])
    files: list[Path] = []

    if target.is_dir():
        files = sorted(target.rglob("*.yaml")) + sorted(target.rglob("*.yml"))
    elif target.is_file():
        files = [target]
    else:
        print(f"Not found: {target}")
        sys.exit(1)

    total_errors = 0
    for f in files:
        errs = validate_skill_yaml(f)
        if errs:
            print(
                f"\n✗ {f.relative_to(Path.cwd()) if f.is_relative_to(Path.cwd()) else f}"
            )
            for e in errs:
                print(f"  - {e}")
            total_errors += len(errs)
        else:
            print(
                f"✓ {f.relative_to(Path.cwd()) if f.is_relative_to(Path.cwd()) else f}"
            )

    print(f"\n{'─' * 40}")
    print(f"Files: {len(files)}  Errors: {total_errors}")
    sys.exit(1 if total_errors > 0 else 0)


if __name__ == "__main__":
    main()
