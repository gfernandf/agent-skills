#!/usr/bin/env python3
"""DC4 — Validate JSON schemas in docs/schemas/ are well-formed.

Loads every ``*.schema.json`` file, verifies it is valid JSON and a
valid JSON Schema (Draft 2020-12 / Draft 7), and optionally validates
sample data from docs/schemas/examples/.

Usage:
    python tooling/validate_json_schemas.py

Exit codes:
    0 — all schemas valid
    1 — validation errors found
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = ROOT / "docs" / "schemas"
EXAMPLES_DIR = SCHEMAS_DIR / "examples"


def _validate_schema_structure(path: Path) -> list[str]:
    """Return list of errors for a single schema file."""
    errors: list[str] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            schema = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"{path.name}: invalid JSON — {e}")
        return errors

    if not isinstance(schema, dict):
        errors.append(f"{path.name}: root must be an object")
        return errors

    # Basic JSON Schema structure checks
    if "type" not in schema and "properties" not in schema and "$ref" not in schema and "oneOf" not in schema and "anyOf" not in schema:
        errors.append(f"{path.name}: missing 'type', 'properties', '$ref', or 'oneOf'/'anyOf' at root")

    # If jsonschema is installed, use it for full meta-validation
    try:
        import jsonschema
        jsonschema.Draft7Validator.check_schema(schema)
    except ImportError:
        pass  # jsonschema not installed — structural check only
    except jsonschema.SchemaError as e:
        errors.append(f"{path.name}: invalid JSON Schema — {e.message}")

    return errors


def main() -> int:
    if not SCHEMAS_DIR.exists():
        print(f"Schema directory not found: {SCHEMAS_DIR}")
        return 1

    schema_files = sorted(SCHEMAS_DIR.glob("*.schema.json"))
    if not schema_files:
        print("No schema files found.")
        return 0

    all_errors: list[str] = []
    for path in schema_files:
        all_errors.extend(_validate_schema_structure(path))

    # Validate examples against schemas if both exist
    if EXAMPLES_DIR.exists():
        try:
            import jsonschema
            for example_path in sorted(EXAMPLES_DIR.glob("*.json")):
                # Convention: example name matches schema name
                # e.g. SkillSpec.example.json → SkillSpec.schema.json
                schema_name = example_path.stem.replace(".example", "") + ".schema.json"
                schema_path = SCHEMAS_DIR / schema_name
                if not schema_path.exists():
                    continue
                with schema_path.open() as f:
                    schema = json.load(f)
                with example_path.open() as f:
                    example = json.load(f)
                try:
                    jsonschema.validate(example, schema)
                except jsonschema.ValidationError as e:
                    all_errors.append(f"{example_path.name}: failed validation — {e.message}")
        except ImportError:
            pass

    if all_errors:
        print(f"SCHEMA VALIDATION FAILED ({len(all_errors)} errors):\n")
        for e in all_errors:
            print(f"  - {e}")
        return 1

    print(f"All {len(schema_files)} schemas are valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
