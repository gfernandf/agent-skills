#!/usr/bin/env python
"""Quick check of decision-related capabilities and any registration issues."""

import sys
import traceback

try:
    from sdk.embedded import list_capabilities, list_skills

    print("✓ SDK imported successfully")

    caps = list_capabilities()
    print(f"✓ Loaded {len(caps)} capabilities")

    decision_caps = [c for c in caps if "decision" in c.get("id", "").lower()]
    print(f"✓ Found {len(decision_caps)} decision-related capabilities:")
    for cap in decision_caps:
        print(f"  - {cap.get('id')}")

    print("\n✓ Checking skills...")
    skills = list_skills()
    print(f"✓ Loaded {len(skills)} skills")

    decision_skills = [s for s in skills if "decision" in s.get("id", "").lower()]
    print(f"✓ Found {len(decision_skills)} decision-related skills:")
    for skill in decision_skills:
        print(f"  - {skill.get('id')}: {skill.get('description', '')[:60]}")

except Exception as e:
    print(f"✗ Error: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n✓✓✓ All checks passed")
