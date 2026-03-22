# services/official/

YAML service descriptors for the official baselines.

Each descriptor declares the protocol kind (`pythoncall`, `openapi`, `mcp`, `openrpc`)
and references the actual implementation. For `pythoncall` services, the `module`
field points to a Python module in `official_services/`.

See [official_services/README.md](../../official_services/README.md) for the
implementation side.
