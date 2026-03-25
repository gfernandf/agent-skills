# Streaming SSE — Server-Sent Events

> Real-time event streaming during skill execution.

## Endpoint

```
POST /v1/skills/{skill_id}/execute/stream
```

Same request body as `/execute`. Response is a **Server-Sent Events** stream.

## Request

```bash
curl -N -X POST http://localhost:8080/v1/skills/my.skill/execute/stream \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_KEY" \
  -d '{"inputs": {"text": "Hello world"}}'
```

## Response Headers

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
```

## Event Format

Each engine event is emitted as an SSE event:

```
event: step_start
data: {"type":"step_start","message":"Starting step 'analyze'.","timestamp":"2026-03-25T12:00:00Z","step_id":"analyze","trace_id":"abc-123","data":null}

event: step_completed
data: {"type":"step_completed","message":"Step 'analyze' completed.","timestamp":"2026-03-25T12:00:01Z","step_id":"analyze","trace_id":"abc-123","data":{"produced_output":{"summary":"..."}}}

event: done
data: {"skill_id":"my.skill","status":"completed","outputs":{"result":"..."},"trace_id":"abc-123"}
```

## Event Types

| Event              | Description                          |
| ------------------ | ------------------------------------ |
| `skill_start`      | Skill execution begins               |
| `step_start`       | A step starts executing              |
| `step_completed`   | A step finished successfully         |
| `step_skipped`     | A step was skipped (condition false)  |
| `step_degraded`    | A step was degraded (safety gate)    |
| `step_failed`      | A step failed                        |
| `skill_completed`  | Skill execution finished             |
| `done`             | Final event — contains the result    |

## Client Integration

### JavaScript (EventSource not applicable for POST — use fetch)

```javascript
const response = await fetch('/v1/skills/my.skill/execute/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'x-api-key': 'KEY' },
  body: JSON.stringify({ inputs: { text: 'hello' } }),
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  const lines = buffer.split('\n');
  buffer = lines.pop();
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const event = JSON.parse(line.slice(6));
      console.log(event.type, event.message);
    }
  }
}
```

### Python

```python
import requests

with requests.post(
    'http://localhost:8080/v1/skills/my.skill/execute/stream',
    json={'inputs': {'text': 'hello'}},
    headers={'x-api-key': 'KEY'},
    stream=True,
) as resp:
    for line in resp.iter_lines(decode_unicode=True):
        if line.startswith('data: '):
            import json
            event = json.loads(line[6:])
            print(event['type'], event.get('message', ''))
```

## Notes

- The connection stays open until `event: done` is emitted.
- On error, the engine still emits `step_failed` events before `done`.
- The `done` event always contains the final result (same shape as `/execute` response).
- Auth and rate limiting apply the same as for `/execute`.
- `execution_channel` is automatically set to `"http-stream"`.
