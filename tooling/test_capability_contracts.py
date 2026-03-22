#!/usr/bin/env python3
"""
Contract tests for all capabilities.

For each capability, verifies:
1. OUTPUT SHAPE   — all output keys declared in the schema are present in the result.
2. OUTPUT TYPES   — output values match the declared types (best-effort).
3. GRACEFUL ERROR — calling with missing/empty required input does not raise an
                    unhandled exception; the service returns a structured dict.

Exit codes:
  0 — all contract checks passed
  1 — at least one contract violation detected
"""

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_ROOT = ROOT.parent / "agent-skill-registry"

sys.path.insert(0, str(ROOT))

import test_capabilities_batch as batch
from runtime.binding_registry import BindingRegistry
from runtime.capability_loader import YamlCapabilityLoader

# ---------------------------------------------------------------------------
# Type mapping: capability YAML type → Python type(s)
# ---------------------------------------------------------------------------
_TYPE_MAP: dict[str, tuple] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


# ---------------------------------------------------------------------------
# Per-capability invalid input overrides
# (used for the graceful-error contract test)
# ---------------------------------------------------------------------------
INVALID_INPUTS: dict[str, dict] = {
    "code.snippet.execute":          {"code": "", "language": "python"},
    "web.page.fetch":             {"url": "ftp://not-allowed.example.com"},
    "pdf.document.read":              {"path": "/nonexistent/path/file.pdf"},
    "audio.speech.transcribe":      {"audio": ""},
    "fs.file.read":               {"path": "", "mode": "text"},
    "image.caption.generate":{"image": None},
    "text.content.summarize":        {"text": ""},
    "code.source.format":           {"code": "", "language": "python"},
    "data.json.parse":       {"text": ""},
    "data.schema.validate":  {"data": {}, "schema": {}},
}


def _make_empty_input(capability_id: str, cap_spec) -> dict:
    """Build a minimal invalid input by stripping required fields."""
    override = INVALID_INPUTS.get(capability_id)
    if override is not None:
        return override
    # Generic fallback: empty values for all required inputs
    result = {}
    for field_name, field_spec in cap_spec.inputs.items():
        if field_spec.required:
            result[field_name] = None
    return result


def _check_output_shape(capability_id: str, declared_outputs: dict, result: Any) -> list[str]:
    """Return a list of violations (empty = OK).

    Only required outputs (field.required == True) are enforced — optional
    outputs are implementation-defined and may be absent.
    """
    violations = []
    if not isinstance(result, dict):
        violations.append(f"Result is not a dict: {type(result).__name__}")
        return violations

    for key, field_spec in declared_outputs.items():
        if field_spec.required and key not in result:
            violations.append(f"Missing required output key: '{key}'")

    return violations


def _check_output_types(capability_id: str, declared_outputs: dict, result: Any) -> list[str]:
    """Return a list of violations (empty = OK). None values are skipped."""
    violations = []
    if not isinstance(result, dict):
        return violations  # Already reported in shape check

    for key, field_spec in declared_outputs.items():
        value = result.get(key)
        if value is None:
            continue  # None/missing values are handled by shape check
        python_types = _TYPE_MAP.get(field_spec.type)
        if python_types is None:
            continue  # Unknown type, skip
        if not isinstance(value, python_types):
            violations.append(
                f"Output '{key}' expected type {field_spec.type}, "
                f"got {type(value).__name__} ({repr(value)[:60]})"
            )

    return violations


def _check_graceful_error(capability_id: str, binding, cap_spec) -> list[str]:
    """Return a list of violations (empty = OK)."""
    violations = []
    invalid_input = _make_empty_input(capability_id, cap_spec)

    try:
        success, reason, result = batch.call_capability(capability_id, binding, invalid_input)
        # We expect either:
        # - success=False with a non-empty reason (structured error message)
        # - success=True with a valid structured response (service handled it gracefully)
        # What we do NOT want: an unhandled exception (already caught by call_capability)
        if result is None and success:
            violations.append("Returned success=True but result is None with invalid input.")
    except Exception as e:
        violations.append(f"Unhandled exception with invalid input: {type(e).__name__}: {e}")

    return violations


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_contract_tests():
    capability_loader = YamlCapabilityLoader(REGISTRY_ROOT)
    binding_registry = BindingRegistry(ROOT, REGISTRY_ROOT)
    all_capabilities = capability_loader.get_all_capabilities()

    results = {"pass": [], "fail": []}
    total_checks = 0

    print(f"Running contract tests for {len(all_capabilities)} capabilities...\n")

    for capability_id in sorted(all_capabilities.keys()):
        cap_spec = all_capabilities[capability_id]
        binding = batch.select_binding_for_capability(binding_registry, capability_id)

        if binding is None:
            results["fail"].append({
                "id": capability_id,
                "violations": ["No binding found — cannot run contract tests."],
            })
            continue

        test_input = batch.TEST_DATA.get(capability_id)

        capability_violations = []

        # --- 1. OUTPUT SHAPE + TYPES (requires valid input) ---
        if test_input:
            success, reason, result = batch.call_capability(capability_id, binding, test_input)
            if success and result is not None:
                total_checks += 1
                shape_violations = _check_output_shape(capability_id, cap_spec.outputs, result)
                capability_violations.extend(shape_violations)

                total_checks += 1
                type_violations = _check_output_types(capability_id, cap_spec.outputs, result)
                capability_violations.extend(type_violations)
            else:
                capability_violations.append(
                    f"Happy-path call failed (cannot check shape/types): {reason}"
                )
        else:
            capability_violations.append("No test data — skipping shape/type checks.")

        # --- 2. GRACEFUL ERROR ---
        total_checks += 1
        graceful_violations = _check_graceful_error(capability_id, binding, cap_spec)
        capability_violations.extend(graceful_violations)

        if capability_violations:
            results["fail"].append({"id": capability_id, "violations": capability_violations})
        else:
            results["pass"].append(capability_id)

    return results, total_checks


def print_results(results: dict, total_checks: int):
    print("=" * 70)
    print("CONTRACT TEST RESULTS")
    print("=" * 70)

    print(f"\n✅ PASS ({len(results['pass'])})")
    print("-" * 70)
    for cap_id in results["pass"]:
        print(f"  {cap_id}")

    print(f"\n❌ FAIL ({len(results['fail'])})")
    print("-" * 70)
    for item in results["fail"]:
        print(f"  {item['id']}")
        for v in item["violations"]:
            print(f"      • {v}")

    print("\n" + "=" * 70)
    total = len(results["pass"]) + len(results["fail"])
    print(
        f"SUMMARY: {len(results['pass'])}/{total} capabilities passed | "
        f"{total_checks} checks run | {len(results['fail'])} violations"
    )
    print("=" * 70 + "\n")

    return len(results["fail"]) == 0


def main():
    try:
        results, total_checks = run_contract_tests()
        ok = print_results(results, total_checks)
        return 0 if ok else 1
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
