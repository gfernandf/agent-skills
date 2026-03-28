"""Example: Use agent-skills capabilities as OpenAI function-calling tools.

Requires:
    pip install openai

Usage:
    export OPENAI_API_KEY=sk-...
    python examples/openai_tools_example.py
"""

from sdk import as_openai_tools, execute_openai_tool_call

# Build tool definitions for GPT
tools = as_openai_tools(["text.content.summarize", "data.json.parse"])

print(f"Registered {len(tools)} tools for OpenAI:")
for t in tools:
    print(f"  - {t['function']['name']}: {t['function'].get('description', '')[:80]}")

# Simulated tool call (replace with real API call when OPENAI_API_KEY is set)
print("\n--- Simulated execution ---")
import json

result = execute_openai_tool_call(
    "text_content_summarize",
    json.dumps(
        {
            "text": "Agent-skills is a runtime for composable AI agent skills.",
            "max_length": 30,
        }
    ),
)
print(f"Result: {result}")
