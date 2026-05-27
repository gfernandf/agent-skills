import json
import os

filepath = "artifacts/cognitive_e2e_contract_report.json"
if not os.path.exists(filepath):
    print(f"File not found: {filepath}")
    exit(1)

with open(filepath, "r") as f:
    data = json.load(f)

if isinstance(data, dict):
    results = data.get("capabilities", data.get("results", []))
    summary = data.get("summary", {})
    total = summary.get("total", len(results))
    passed = summary.get(
        "passed", sum(1 for r in results if r.get("status") == "passed")
    )
    failed = summary.get(
        "failed", sum(1 for r in results if r.get("status") == "failed")
    )
else:
    results = data
    total = len(results)
    passed = sum(1 for r in results if r.get("status") == "passed")
    failed = sum(1 for r in results if r.get("status") == "failed")

print(f"TOTAL: {total}")
print(f"PASSED: {passed}")
print(f"FAILED: {failed}")

if failed > 0:
    for r in results:
        if r.get("status") == "failed":
            print(f"ID: {r.get('id')} - Error: {r.get('error') or r.get('message')}")
elif total == 73:
    print("CONFIRMED 73/73")
    for r in results[:10]:
        # Print only ID and keys that aren't the large 'output' or 'input' if they exist
        filtered = {
            k: v for k, v in r.items() if k not in ["input", "output", "full_response"]
        }
        print(json.dumps(filtered))
else:
    # Print sample anyway if total is different but failed is 0
    print(f"Total is {total}")
    for r in results[:10]:
        filtered = {
            k: v for k, v in r.items() if k not in ["input", "output", "full_response"]
        }
        print(json.dumps(filtered))
