#!/usr/bin/env python3
"""
Validation script to detect binding-capability input mismatches.

This script scans all bindings and verifies that their request templates
only reference inputs that exist in their corresponding capabilities.
"""

import sys
from pathlib import Path

# Add runtime to path
runtime_root = Path(__file__).parent / "runtime"
sys.path.insert(0, str(runtime_root))

from runtime.binding_registry import BindingRegistry
from runtime.capability_loader import YamlCapabilityLoader


def validate_binding_inputs():
    """Validate that all bindings reference valid capability inputs."""

    # Initialize components
    registry_root = Path(__file__).parent.parent / "agent-skill-registry"
    runtime_root = Path(__file__).parent

    capability_loader = YamlCapabilityLoader(registry_root)
    binding_registry = BindingRegistry(runtime_root, registry_root)

    # Get all bindings
    all_bindings = binding_registry.list_bindings()

    print(f"Validating {len(all_bindings)} bindings...")

    issues_found = []

    for binding in all_bindings:
        binding_id = binding.id
        try:
            # Get the capability
            capability = capability_loader.get_capability(binding.capability_id)

            # Check request template inputs
            request_template = binding.request_template
            capability_inputs = set(capability.inputs.keys())

            # Find referenced inputs in the template
            referenced_inputs = set()
            _collect_template_inputs(request_template, referenced_inputs)

            # Check for missing inputs
            missing_inputs = referenced_inputs - capability_inputs
            if missing_inputs:
                issues_found.append({
                    'binding_id': binding_id,
                    'capability_id': binding.capability_id,
                    'missing_inputs': sorted(missing_inputs),
                    'capability_inputs': sorted(capability_inputs),
                    'referenced_inputs': sorted(referenced_inputs)
                })

        except Exception as e:
            issues_found.append({
                'binding_id': binding_id,
                'error': str(e)
            })

    return issues_found


def _collect_template_inputs(template: dict, inputs: set):
    """Recursively collect all input.* references from a template."""
    for key, value in template.items():
        if isinstance(value, str) and value.startswith("input."):
            input_name = value[len("input."):]
            inputs.add(input_name)
        elif isinstance(value, dict):
            _collect_template_inputs(value, inputs)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _collect_template_inputs(item, inputs)


def main():
    issues = validate_binding_inputs()

    if not issues:
        print("[OK] All bindings are valid!")
        return 0

    print(f"[FAIL] Found {len(issues)} binding validation issues:")
    print()

    for issue in issues:
        if 'error' in issue:
            print(f"Binding: {issue['binding_id']}")
            print(f"  Error: {issue['error']}")
        else:
            print(f"Binding: {issue['binding_id']}")
            print(f"  Capability: {issue['capability_id']}")
            print(f"  Missing inputs: {', '.join(issue['missing_inputs'])}")
            print(f"  Available inputs: {', '.join(issue['capability_inputs'])}")
            print(f"  Referenced inputs: {', '.join(issue['referenced_inputs'])}")
        print()

    return 1


if __name__ == "__main__":
    sys.exit(main())