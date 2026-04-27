"""Sweep all skills with `cli test` and report pass/fail."""

import subprocess
import sys
import json

# Get all skill IDs
r = subprocess.run(
    [sys.executable, "-m", "cli.main", "list", "--json"],
    capture_output=True,
    text=True,
)
data = json.loads(r.stdout)
skills = [s["id"] for s in data["skills"]]

results = {"pass": [], "fail": []}
for sid in skills:
    print(f"Testing {sid}...", flush=True)
    try:
        r2 = subprocess.run(
            [sys.executable, "-m", "cli.main", "test", sid],
            capture_output=True,
            text=True,
            timeout=120,
        )
        combined = r2.stdout + r2.stderr
        if "PASS" in combined or '"status": "completed"' in combined:
            results["pass"].append(sid)
            print("  PASS", flush=True)
        else:
            snippet = combined[-500:] if len(combined) > 500 else combined
            results["fail"].append((sid, snippet))
            print("  FAIL", flush=True)
    except subprocess.TimeoutExpired:
        results["fail"].append((sid, "TIMEOUT after 60s"))
        print("  TIMEOUT", flush=True)

print(f"\n{'=' * 60}")
print("SKILL TEST SUMMARY")
print(f"{'=' * 60}")
print(f"PASS: {len(results['pass'])}/{len(skills)}")
print(f"FAIL: {len(results['fail'])}/{len(skills)}")
if results["fail"]:
    print("\nFailed skills:")
    for sid, err in results["fail"]:
        # Clean up for readability
        short = err.replace("\n", " | ")[:300]
        print(f"  {sid}:")
        print(f"    {short}")
