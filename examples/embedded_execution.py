"""Example: Use agent-skills directly via the embedded SDK (no server needed).

Usage:
    python examples/embedded_execution.py
"""

from sdk import execute, execute_capability, list_capabilities

# List available capabilities
caps = list_capabilities()
print(f"Available capabilities: {len(caps)}")
for c in caps[:5]:
    print(f"  - {c['id']}: {c.get('description', '')[:60]}")
print("  ...")

# Execute a single capability directly
print("\n--- Execute capability ---")
result = execute_capability(
    "text.content.summarize",
    {
        "text": "Agent-skills is a deterministic execution engine for composable AI agent skills.",
        "max_length": 30,
    },
)
print(f"Capability result: {result}")

# Execute a full skill (multi-step workflow)
print("\n--- Execute skill ---")
result = execute(
    "text.summarize-plain-input",
    {
        "text": "Agent-skills is a deterministic execution engine for composable AI agent skills.",
        "max_length": 30,
    },
)
print(f"Skill result: {result}")
