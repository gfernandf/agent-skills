"""
Example: Connecting Claude to agent-skills
==========================================

This example shows how to wire Claude (via the Anthropic API) to execute
skills and capabilities through agent-skills' embedded runtime.

No HTTP server needed — everything runs in-process.

Requirements:
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-ant-...

Usage:
    python examples/claude_agent_example.py
"""

from __future__ import annotations

import json
import os


def main():
    # ──────────────────────────────────────────────────────────────
    # Step 1: Get tool definitions from agent-skills
    # ──────────────────────────────────────────────────────────────
    from sdk.embedded import as_anthropic_tools

    # Pick which capabilities Claude can use (or pass None for all)
    tools, dispatch = as_anthropic_tools([
        "text.content.summarize",
        "data.json.parse",
    ])

    # `tools` is a list of dicts ready for Anthropic's API:
    #
    #   [
    #     {
    #       "name": "text_content_summarize",
    #       "description": "Produce a condensed version of text...",
    #       "input_schema": {
    #         "type": "object",
    #         "properties": {
    #           "text": {"type": "string"},
    #           "max_length": {"type": "integer"}
    #         },
    #         "required": ["text"]
    #       }
    #     },
    #     ...
    #   ]
    #
    # `dispatch` is a dict mapping tool_name → callable:
    #
    #   {
    #     "text_content_summarize": <function>,
    #     "data_json_parse": <function>,
    #   }

    print(f"Registered {len(tools)} tools for Claude:")
    for t in tools:
        print(f"  - {t['name']}: {t['description'][:60]}...")

    # ──────────────────────────────────────────────────────────────
    # Step 2: Run the agentic loop
    # ──────────────────────────────────────────────────────────────
    import anthropic

    client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY env var

    messages = [
        {
            "role": "user",
            "content": (
                "Summarize the following text in one sentence:\n\n"
                "Machine learning is a subset of artificial intelligence that "
                "focuses on building systems that learn from data. Instead of "
                "being explicitly programmed, these systems improve their "
                "performance through experience. Applications range from image "
                "recognition to natural language processing and autonomous "
                "vehicles."
            ),
        }
    ]

    print("\n--- Sending to Claude ---")

    # Agentic loop: keep going until Claude stops calling tools
    while True:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            tools=tools,
            messages=messages,
        )

        # Collect all content blocks
        tool_calls = []
        text_output = []

        for block in response.content:
            if block.type == "text":
                text_output.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(block)

        # If there are text blocks and no tool calls, we're done
        if not tool_calls:
            print("\n--- Claude's response ---")
            print("\n".join(text_output))
            break

        # Process each tool call
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for call in tool_calls:
            print(f"\n  [Tool call] {call.name}({json.dumps(call.input, ensure_ascii=False)[:100]})")

            # Execute via agent-skills embedded runtime
            result = dispatch[call.name](**call.input)

            print(f"  [Result]    {json.dumps(result, ensure_ascii=False)[:100]}")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": json.dumps(result),
            })

        messages.append({"role": "user", "content": tool_results})


# ──────────────────────────────────────────────────────────────
# Minimal version (no agentic loop, just show the wiring)
# ──────────────────────────────────────────────────────────────

def minimal_example():
    """Simplest possible connection — no API call, just shows the plumbing."""
    from sdk.embedded import as_anthropic_tools

    tools, dispatch = as_anthropic_tools(["text.content.summarize"])

    # This is what you'd pass to client.messages.create(tools=...)
    print("Tool definition for Anthropic API:")
    print(json.dumps(tools, indent=2))

    # This is how you'd execute when Claude returns a tool_use block:
    # result = dispatch["text_content_summarize"](text="Hello world", max_length=20)
    print("\nTo execute: dispatch['text_content_summarize'](text='...', max_length=20)")


if __name__ == "__main__":
    if os.environ.get("ANTHROPIC_API_KEY"):
        main()
    else:
        print("No ANTHROPIC_API_KEY set — running minimal example.\n")
        minimal_example()
