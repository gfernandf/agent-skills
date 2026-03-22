# official_services/

Python implementations of the official service baselines.

Each module in this directory exposes callable functions that are
invoked by `pythoncall` bindings through the runtime's `PythonCallInvoker`.

The corresponding **service descriptors** (YAML) live in `services/official/`.
Each descriptor references the Python module via its `module` field:

```yaml
# services/official/text_baseline.yaml
kind: pythoncall
module: official_services.text_baseline
```

## Naming convention

| Descriptor (YAML)                        | Implementation (Python)             |
|------------------------------------------|-------------------------------------|
| `services/official/text_baseline.yaml`   | `official_services/text_baseline.py`|
| `services/official/web_baseline.yaml`    | `official_services/web_baseline.py` |

## Adding a new service

1. Create the Python module here with the callable operations.
2. Create a matching YAML descriptor in `services/official/`.
3. Create one or more bindings in `bindings/official/<capability_id>/`.
