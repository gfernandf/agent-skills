"""A2 — Formal plugin protocol definitions.

Defines typed Protocol classes for each plugin extension point so that
``discover_plugins()`` can verify interface compliance at load time.

Usage::

    from runtime.plugin_protocols import AuthBackendProtocol, InvokerProtocol

    class MyAuth:
        def authenticate(self, headers: dict) -> Identity | None: ...
        def authorize(self, identity: Identity, method: str, path: str) -> bool: ...

    assert isinstance(MyAuth(), AuthBackendProtocol)  # structural check
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AuthBackendProtocol(Protocol):
    """Extension point: pluggable authentication backend."""

    def authenticate(self, headers: dict[str, str]) -> Any:
        """Return an Identity-like object or None if unauthenticated."""
        ...

    def authorize(self, identity: Any, method: str, path: str) -> bool:
        """Return True if the identity is allowed for the given route."""
        ...


@runtime_checkable
class InvokerProtocol(Protocol):
    """Extension point: pluggable capability invoker (OpenAPI, MCP, etc.)."""

    def invoke(self, request: Any) -> Any:
        """Execute an invocation request and return a response."""
        ...


@runtime_checkable
class BindingSourceProtocol(Protocol):
    """Extension point: pluggable binding/service source."""

    def list_bindings(self, capability_id: str) -> list[Any]:
        """Return available bindings for a given capability."""
        ...


# Map of entry-point group → expected protocol
PLUGIN_PROTOCOL_MAP: dict[str, type] = {
    "agent_skills.auth": AuthBackendProtocol,
    "agent_skills.invoker": InvokerProtocol,
    "agent_skills.binding_source": BindingSourceProtocol,
}


def validate_plugin(group: str, name: str, obj: Any) -> list[str]:
    """Check whether *obj* satisfies the protocol for *group*.

    Returns a list of violation messages (empty = compliant).
    """
    protocol_cls = PLUGIN_PROTOCOL_MAP.get(group)
    if protocol_cls is None:
        return []

    violations: list[str] = []
    if not isinstance(obj, protocol_cls):
        violations.append(
            f"Plugin '{name}' in group '{group}' does not implement "
            f"{protocol_cls.__name__}."
        )
    return violations
