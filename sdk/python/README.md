# agent-skills-client (Python)

Lightweight, zero-dependency Python client for the agent-skills HTTP API.

## Installation

Copy `agent_skills_client.py` into your project, or install agent-skills:

```bash
pip install agent-skills
```

## Quick Start

```python
from sdk.python.agent_skills_client import AgentSkillsClient

client = AgentSkillsClient("http://localhost:8080", api_key="my-key")

# Execute a skill
result = client.execute("text.content.summarize", {"text": "Long document..."})
print(result["outputs"]["summary"])

# Discover skills by intent
matches = client.discover("summarize a document")

# Async execution with polling
run = client.execute_async("text.content.summarize", {"text": "Very long..."})
completed = client.wait_for_run(run["run_id"], timeout=60)

# SSE streaming
for event in client.execute_stream("text.content.summarize", {"text": "..."}):
    print(event["event"], event["data"])
```

## API

| Method | Description |
|--------|-------------|
| `health()` | Health check |
| `list_skills()` | List all skills |
| `describe(skill_id)` | Describe a skill |
| `execute(skill_id, inputs)` | Synchronous execution |
| `execute_async(skill_id, inputs)` | Launch async execution |
| `get_run(run_id)` | Get run status |
| `list_runs()` | List all runs |
| `wait_for_run(run_id)` | Poll until complete |
| `execute_stream(skill_id, inputs)` | SSE streaming |
| `discover(intent)` | Discover skills by intent |

## Dependencies

None — uses only Python stdlib (`urllib.request`, `json`).
