# Webhooks

agent-skills supports a push-based event system via HTTP webhooks.
When a skill execution completes or fails, registered endpoints receive
a signed JSON payload automatically.

## Event types

| Event | Fired when |
|---|---|
| `skill.started` | A skill execution begins |
| `skill.completed` | A skill finishes successfully |
| `skill.failed` | A skill execution fails |
| `run.completed` | An async run finishes |
| `run.failed` | An async run fails |
| `*` | Wildcard — receive all events |

## Managing subscriptions

### Create a subscription

```http
POST /v1/webhooks
Content-Type: application/json
X-API-Key: <key>

{
  "url": "https://example.com/hooks/agent-skills",
  "events": ["skill.completed", "skill.failed"],
  "secret": "my-shared-secret"
}
```

Response `201 Created`:
```json
{
  "id": "wh-abc123",
  "url": "https://example.com/hooks/agent-skills",
  "events": ["skill.completed", "skill.failed"],
  "active": true
}
```

### List subscriptions

```http
GET /v1/webhooks
X-API-Key: <key>
```

### Delete a subscription

```http
DELETE /v1/webhooks/wh-abc123
X-API-Key: <key>
```

## Payload format

Each delivery is a `POST` with `Content-Type: application/json`:

```json
{
  "event": "skill.completed",
  "data": {
    "skill_id": "text.summarize",
    "status": "completed",
    "outputs": ["summary"],
    "duration_ms": 1234.5
  },
  "timestamp": 1711382400.123,
  "trace_id": "abc-def-123"
}
```

## Signature verification

When a `secret` is configured, every delivery includes an
`X-Webhook-Signature` header:

```
X-Webhook-Signature: sha256=<hex-digest>
```

Verify by computing `HMAC-SHA256(secret, raw_body)` and comparing:

```python
import hmac, hashlib

def verify(body: bytes, secret: str, header: str) -> bool:
    expected = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, header)
```

## Retry policy

Failed deliveries (non-2xx response or network error) are retried up to
3 times with exponential backoff (2s → 4s → 8s). Delivery is
fire-and-forget on daemon threads — it never blocks skill execution.

## Limits

- Maximum 100 subscriptions per server instance.
- Delivery timeout: 10 seconds per attempt.
