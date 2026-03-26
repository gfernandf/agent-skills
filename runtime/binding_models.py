from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ServiceDescriptor:
    """
    Runtime-normalized description of a concrete service available to bindings.

    Supported kinds in v1:
    - openapi
    - mcp
    - openrpc
    - pythoncall
    """

    id: str
    kind: str
    spec_ref: str | None = None
    auth_ref: str | None = None
    base_url: str | None = None
    server: str | None = None
    module: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = "official"  # official | local
    source_file: str | None = None


@dataclass(frozen=True)
class BindingSpec:
    """
    Runtime-normalized binding connecting one capability to one service operation.

    v1 invariants:
    - one binding implements one capability
    - one binding targets one service
    - one binding invokes one operation
    """

    id: str
    capability_id: str
    service_id: str
    protocol: str
    operation_id: str
    request_template: dict[str, Any]
    response_mapping: dict[str, str]
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = "official"  # official | local | candidate
    source_file: str | None = None


@dataclass(frozen=True)
class ResolvedBinding:
    """
    Result of runtime binding resolution for a capability in a specific instance.

    Two dimensions are tracked separately:
    - binding_source: where the binding comes from
    - selection_source: why this binding was chosen
    """

    capability_id: str
    binding_id: str
    service_id: str
    operation_id: str
    protocol: str
    binding_source: str  # official | local | candidate
    selection_source: str  # local_selection | environment_preferred | official_default


@dataclass(frozen=True)
class InvocationRequest:
    """
    Concrete invocation request sent to a protocol-specific invoker.
    """

    protocol: str
    service: ServiceDescriptor
    binding: BindingSpec
    operation_id: str
    payload: dict[str, Any]
    context_metadata: dict[str, Any] = field(default_factory=dict)
    cancel_event: threading.Event | None = None


@dataclass(frozen=True)
class InvocationResponse:
    """
    Protocol-agnostic invocation result returned by an invoker.
    """

    status: str
    raw_response: Any
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OverrideIntent:
    """
    User-declared local intent loaded from .agent-skills/overrides.yaml.
    """

    capabilities: tuple[str, ...]
    binding_id: str | None = None
    service_id: str | None = None
    mode: str = "replace"  # replace | prefer
    source_file: str | None = None
