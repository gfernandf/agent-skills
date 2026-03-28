"""Example: Use agent-skills capabilities as Anthropic Claude tools.

Requires:
    pip install anthropic

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python examples/anthropic_tools_example.py
"""

from sdk import as_anthropic_tools, execute_anthropic_tool_call

# Build tool definitions for Claude
tools = as_anthropic_tools(["text.content.summarize", "text.language.detect"])

print(f"Registered {len(tools)} tools for Claude:")
for t in tools:
    print(f"  - {t['name']}: {t.get('description', '')[:80]}")

# Simulated tool-use loop (replace with real API call when ANTHROPIC_API_KEY is set)
print("\n--- Simulated execution ---")
result = execute_anthropic_tool_call(
    "text_content_summarize",
    {
        "text": "Agent-skills is a runtime for composable AI agent skills.",
        "max_length": 30,
    },
)
print(f"Result: {result}")
