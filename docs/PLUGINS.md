# Plugin System

agent-skills uses Python [entry points](https://packaging.python.org/en/latest/specifications/entry-points/)
for extensibility. Third-party packages can register custom
authentication backends, protocol invokers, or binding sources.

## Plugin groups

| Group | Purpose | Example |
|---|---|---|
| `agent_skills.auth` | Authentication backends | OAuth, LDAP, custom SSO |
| `agent_skills.invoker` | Protocol invokers | gRPC, GraphQL, custom protocols |
| `agent_skills.binding_source` | Binding/service sources | Community registries, private catalogs |

## Registering a plugin

In your package's `pyproject.toml`:

```toml
[project.entry-points."agent_skills.invoker"]
grpc = "my_package.grpc_invoker:GRPCInvoker"
```

Or in `setup.cfg`:

```ini
[options.entry_points]
agent_skills.invoker =
    grpc = my_package.grpc_invoker:GRPCInvoker
```

## Discovery API

```python
from runtime.plugins import discover_plugins, discover_all

# Discover plugins for a specific group
invokers = discover_plugins("agent_skills.invoker")
# → {"grpc": <class GRPCInvoker>}

# Discover all registered plugins
all_plugins = discover_all()
# → {"agent_skills.auth": {...}, "agent_skills.invoker": {...}, ...}
```

Plugins are discovered at startup by `engine_factory.build_runtime_components()`.
Failed plugin loads are logged as warnings but do not prevent startup.

## Creating an invoker plugin

An invoker must implement the protocol invoker interface:

```python
class GRPCInvoker:
    def invoke(self, request):
        """Execute the invocation and return an InvocationResponse."""
        ...
```

Register it and install your package — it will be discovered automatically
on the next engine startup.

## Creating an auth plugin

An auth backend must be callable as a token verifier:

```python
def my_verifier(token: str) -> Identity | None:
    """Verify token and return Identity or None."""
    ...
```

Pass it to `AuthMiddleware(token_verifier=my_verifier)`.
