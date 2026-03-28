"""Example: Use agent-skills capabilities as Google Gemini tools.

Requires:
    pip install google-genai

Usage:
    export GOOGLE_API_KEY=...
    python examples/gemini_tools_example.py
"""

from sdk import as_gemini_tools, execute_gemini_tool_call

# Build tool definitions for Gemini
tools = as_gemini_tools(["text.content.summarize"])

print(f"Registered {len(tools)} tools for Gemini:")
for t in tools:
    print(f"  - {t.get('name', 'unknown')}")

# Simulated tool call (replace with real API call when GOOGLE_API_KEY is set)
print("\n--- Simulated execution ---")
result = execute_gemini_tool_call(
    "text_content_summarize",
    {
        "text": "Agent-skills is a runtime for composable AI agent skills.",
        "max_length": 30,
    },
)
print(f"Result: {result}")
