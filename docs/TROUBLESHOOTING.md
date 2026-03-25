# Troubleshooting

Common issues and solutions for the agent-skills runtime.

---

## Startup & Configuration

### Server won't start — "Address already in use"

Another process is occupying port 8080.

```bash
# Find the process
# Linux/macOS:
lsof -i :8080
# Windows:
netstat -ano | findstr :8080
```

Kill the process or change the port via `AGENT_SKILLS_PORT`.

### "ModuleNotFoundError: No module named 'runtime'"

You're running from outside the project root. `cd` into the `agent-skills/`
directory or install in editable mode:

```bash
pip install -e .
```

---

## Binding & Capability Errors

### "No binding found for capability 'X'"

The binding resolution chain found no binding for this capability.

1. Verify the binding YAML exists under `bindings/official/<capability_id>/`.
2. Run `python validate_bindings.py` to check binding validity.
3. If using local overrides, verify `.agent-skills/overrides.yaml`.

### "Module 'official_services.X' does not expose callable 'Y'"

The binding references an operation that doesn't exist in the service module.

1. Check the binding's `operation` field matches a function name in the service module.
2. Verify the service descriptor's `module` field points to the right Python module.

### "Service 'X' does not define a base_url"

An OpenAPI binding is trying to invoke a service without a `base_url`.

1. Check `services/official/<service>.yaml` has a `base_url` field.
2. If the URL uses environment substitution (`${VAR}`), ensure the var is set.

---

## Authentication

### "403 Forbidden" on all requests

Auth mode is `enforced` but no API key is provided.

- Set `AGENT_SKILLS_API_KEY` on the server.
- Pass `Authorization: Bearer <key>` in requests.
- Or set `AGENT_SKILLS_AUTH_MODE=disabled` for development.

### Rate limit exceeded (429)

Default: 60 requests per 60-second window per client IP.

- Increase via `AGENT_SKILLS_RATE_LIMIT` and `AGENT_SKILLS_RATE_WINDOW`.
- Behind a proxy? Set `AGENT_SKILLS_TRUSTED_PROXIES` so the real client IP is used.

---

## MCP Issues

### "No MCP client configured for server 'X'"

The server name isn't registered in `DefaultMCPClientRegistry`.

1. For in-process servers, verify `official_mcp_servers/` has a matching module.
2. For subprocess servers, configure `subprocess_servers` in the registry init.

### MCP subprocess hangs

The external MCP server may not be responding on stdio.

1. Test the server manually: `echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | <command>`
2. Check `SubprocessMCPClient` timeout (default: 30s).

---

## Performance

### Slow first request after startup

Expected — Python module imports and binding resolution happen lazily on
first use. Subsequent requests benefit from plan caching and connection pooling.

### High memory usage

- Check audit log size (`artifacts/audit.jsonl`). Run purge if needed.
- Connection pool grows up to 32 sessions. Reduce `_SESSION_POOL_MAX` in
  `runtime/openapi_invoker.py` if needed.

---

## Testing

### `pytest` cannot find tests

Ensure you're in the project root and have dev dependencies:

```bash
pip install -e ".[dev]"
pytest -v
```

### Coverage below threshold

The default threshold is 75%. Focus on `runtime/`, `gateway/`, and
`customer_facing/` modules. Run:

```bash
pytest --cov=runtime --cov=gateway --cov=customer_facing --cov-report=html
```

---

## Docker

### Container exits immediately

Check logs: `docker logs <container>`. Common causes:
- Missing required env vars.
- Port conflict with `--network host`.

### Permission denied inside container

The container runs as non-root user `agentskills`. Ensure mounted volumes
have appropriate permissions:

```bash
docker run -v ./data:/app/artifacts:rw ...
```

---

## Still stuck?

1. Enable debug logging: `AGENT_SKILLS_DEBUG=1`
2. Check `artifacts/` for diagnostic files.
3. Run `python tooling/verify_smoke_capabilities.py` to validate the runtime.
4. Open an issue with the debug output.
