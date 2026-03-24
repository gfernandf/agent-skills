# Service Descriptors & Binding Creation Guide

> How to add a new binding to connect a capability to a service.

---

## Architecture

```
Capability (contract)  →  Binding (wiring)  →  Service (implementation)
   YAML in registry         YAML in agent-skills     Python module or HTTP endpoint
```

A **binding** maps a capability's inputs/outputs to a specific service's
operation. Every capability needs at least one binding to be executable.

---

## 1. Binding YAML format

```yaml
id: python_text_summarize                   # unique binding ID
capability: text.content.summarize           # which capability this serves
service: text_baseline                       # service module name
protocol: pythoncall                         # pythoncall | openapi | mcp | openrpc
operation: summarize_text                    # function name or HTTP operation

request:                                     # input mapping
  text: input.text                           # param_name: input.field_name

response:                                    # output mapping
  summary: response.summary                  # output_field: response.field_name

metadata:
  description: Official baseline binding for text.content.summarize.
  status: stable                             # stable | experimental | deprecated
  fallback_binding_id: python_text_summarize # optional: fallback if this fails
```

### Protocols

| Protocol | `service` points to | `operation` means |
|----------|--------------------|--------------------|
| `pythoncall` | Python module in `official_services/` | Function name |
| `openapi` | Service descriptor ID (see below) | HTTP path (e.g., `chat/completions`) |
| `mcp` | MCP server ID | Tool name |
| `openrpc` | JSON-RPC service ID | Method name |

---

## 2. Creating a Python baseline binding

### Step 1: Implement the function

In `official_services/<service_name>.py`:

```python
def my_operation(text, max_length=None):
    """Baseline implementation (degraded mode)."""
    result = text[:max_length] if max_length else text
    return {"output_field": result}
```

The function must return a `dict` whose keys match the binding's `response`
mapping.

### Step 2: Create the binding YAML

```
bindings/official/<capability_id>/python_<short_name>.yaml
```

Example: `bindings/official/text.content.summarize/python_text_summarize.yaml`

### Step 3: Add test data

In `test_capabilities_batch.py`, add to `TEST_DATA`:

```python
"text.content.summarize": {"text": "Long text here..."},
```

---

## 3. Creating an OpenAI chat binding

For capabilities backed by GPT:

```yaml
id: openapi_text_summarize_openai_chat
capability: text.content.summarize
service: text_openai_chat
protocol: openapi
operation: chat/completions

request:
  model: gpt-4o-mini
  messages:
    - role: system
      content: "You are a summarization assistant. Return only the summary."
    - role: user
      content: input.text
  temperature: 0.2

response:
  summary: response.choices.0.message.content

metadata:
  method: POST
  response_mode: json
  fallback_binding_id: python_text_summarize
  description: OpenAI binding for text.content.summarize.
  status: experimental
```

### For JSON-structured responses

Add `response_format` and use `content_json` in the response mapping:

```yaml
request:
  # ...
  response_format:
    type: json_object

response:
  label: response.choices.0.message.content_json.label
  confidence: response.choices.0.message.content_json.confidence
```

---

## 4. Service descriptors

Service descriptors live in `official_services/` or are referenced by ID.

For **pythoncall** bindings, the service ID is the Python module name under
`official_services/` (e.g., `text_baseline` → `official_services/text_baseline.py`).

For **openapi** bindings, the service ID matches a service descriptor that
defines the base URL, authentication headers, and other HTTP configuration.

---

## 5. Binding selection at runtime

The runtime selects a binding using this priority:

1. **Official default** — from the binding registry's default policy.
2. **User override** — from the host's override intent configuration.
3. **First available** — alphabetical fallback.

When a binding declares `fallback_binding_id`, the runtime can chain to the
fallback on execution failure.

---

## 6. Naming conventions

| Component | Pattern | Example |
|-----------|---------|---------|
| Binding directory | `bindings/official/<capability_id>/` | `bindings/official/text.content.summarize/` |
| Python binding file | `python_<short>.yaml` | `python_text_summarize.yaml` |
| OpenAI binding file | `openapi_<short>_openai_chat.yaml` | `openapi_text_summarize_openai_chat.yaml` |
| Binding ID | Same as filename (minus `.yaml`) | `python_text_summarize` |
| Service function | `snake_case` matching `operation` | `summarize_text()` |

---

## 7. Checklist for adding a new binding

- [ ] Capability exists in the registry (`capabilities/<id>.yaml`).
- [ ] Binding directory: `bindings/official/<capability_id>/`.
- [ ] Binding YAML with correct `id`, `capability`, `service`, `protocol`,
      `operation`, `request`, `response`, `metadata`.
- [ ] Python function returns `dict` with keys matching `response` mapping.
- [ ] Test data added to `test_capabilities_batch.py`.
- [ ] `python test_capabilities_batch.py` passes.
- [ ] If OpenAI binding: `fallback_binding_id` points to the Python baseline.
