"""
Example: Using the agent-skills Python client.

Demonstrates synchronous, asynchronous, and streaming execution.
Requires a running server: agent-skills serve
"""

from sdk.python.agent_skills_client import AgentSkillsClient


def main():
    client = AgentSkillsClient("http://localhost:8080", api_key="my-api-key")

    # ── 1. Health check ──────────────────────────────────
    print("=== Health ===")
    print(client.health())

    # ── 2. List available skills ─────────────────────────
    print("\n=== Skills ===")
    skills = client.list_skills()
    for s in skills.get("skills", [])[:5]:
        print(f"  - {s.get('id', '?')}: {s.get('description', '')[:60]}")

    # ── 3. Synchronous execution ─────────────────────────
    print("\n=== Execute (sync) ===")
    result = client.execute(
        "text.content.generate",
        inputs={"prompt": "Write a haiku about Python"},
    )
    print(f"  Status: {result.get('status')}")
    print(f"  Output: {result.get('outputs', {})}")

    # ── 4. Asynchronous execution ────────────────────────
    print("\n=== Execute (async) ===")
    run = client.execute_async(
        "text.content.generate",
        inputs={"prompt": "Explain agent-skills in one paragraph"},
    )
    run_id = run["run_id"]
    print(f"  Launched run: {run_id}")

    # Poll until done
    final = client.wait_for_run(run_id, poll_interval=0.5, timeout=60)
    print(f"  Final status: {final.get('status')}")
    print(f"  Result: {final.get('result', {})}")

    # ── 5. Streaming execution (SSE) ─────────────────────
    print("\n=== Execute (streaming) ===")
    for event in client.execute_stream(
        "text.content.generate",
        inputs={"prompt": "List 3 benefits of capability contracts"},
    ):
        print(f"  [{event['event']}] {event['data']}")


if __name__ == "__main__":
    main()
