# Async Execution — Run ID Pattern

> Non-blocking skill execution with run tracking.

## Endpoints

### Launch async execution

```
POST /v1/skills/{skill_id}/execute/async
```

Returns immediately with `202 Accepted` and a run ID.

### Check run status

```
GET /v1/runs/{run_id}
```

Returns the current state of a run (running/completed/failed).

### List recent runs

```
GET /v1/runs?limit=50
```

Returns recent runs (newest first, default limit 100).

## Request / Response

### Launch

```bash
curl -X POST http://localhost:8080/v1/skills/my.skill/execute/async \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_KEY" \
  -d '{"inputs": {"text": "Hello world"}}'
```

```json
{
  "run_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "skill_id": "my.skill",
  "status": "running",
  "trace_id": null
}
```

### Poll

```bash
curl http://localhost:8080/v1/runs/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "x-api-key: YOUR_KEY"
```

**Running:**

```json
{
  "run_id": "a1b2c3d4-...",
  "skill_id": "my.skill",
  "status": "running",
  "created_at": "2026-03-25T12:00:00Z",
  "finished_at": null,
  "result": null,
  "error": null
}
```

**Completed:**

```json
{
  "run_id": "a1b2c3d4-...",
  "skill_id": "my.skill",
  "status": "completed",
  "created_at": "2026-03-25T12:00:00Z",
  "finished_at": "2026-03-25T12:00:05Z",
  "result": {
    "skill_id": "my.skill",
    "status": "completed",
    "outputs": {"summary": "..."},
    "trace_id": "..."
  },
  "error": null
}
```

**Failed:**

```json
{
  "run_id": "a1b2c3d4-...",
  "skill_id": "my.skill",
  "status": "failed",
  "created_at": "2026-03-25T12:00:00Z",
  "finished_at": "2026-03-25T12:00:02Z",
  "result": null,
  "error": "Step 'analyze' failed: ..."
}
```

### List

```bash
curl "http://localhost:8080/v1/runs?limit=10" \
  -H "x-api-key: YOUR_KEY"
```

```json
{
  "runs": [
    {"run_id": "...", "skill_id": "...", "status": "completed", ...},
    {"run_id": "...", "skill_id": "...", "status": "running", ...}
  ]
}
```

## Run Lifecycle

```
POST /execute/async
        │
        ▼
   ┌──────────┐
   │  running  │
   └─────┬─────┘
         │
    ┌────┴────┐
    ▼         ▼
┌──────┐  ┌──────┐
│ done │  │failed│
└──────┘  └──────┘
```

## Configuration

| Environment Variable         | Default | Description                       |
| ---------------------------- | ------- | --------------------------------- |
| `AGENT_SKILLS_ASYNC_WORKERS` | `4`     | Thread pool size for async runs   |
| `AGENT_SKILLS_MAX_RUNS`      | `100`   | Max runs kept in memory           |

## Notes

- The run store is **in-memory** — runs are lost when the process restarts.
- The async pool is **separate** from the scheduler's `AGENT_SKILLS_MAX_WORKERS` pool to avoid starvation.
- Runs are evicted FIFO when exceeding `AGENT_SKILLS_MAX_RUNS`.
- This is not a replacement for the audit system — use audit for long-term records.
- Auth and rate limiting apply to all run endpoints.
