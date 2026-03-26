from __future__ import annotations

import threading
import time
from typing import Any

from runtime.binding_models import InvocationRequest, InvocationResponse
from runtime.binding_registry import BindingRegistry
from runtime.binding_resolver import BindingResolver
from runtime.circuit_breaker import CircuitBreakerRegistry, CircuitOpenError
from runtime.metrics import METRICS
from runtime.errors import RuntimeErrorBase
from runtime.request_builder import RequestBuilder
from runtime.response_mapper import ResponseMapper
from runtime.service_resolver import ServiceResolver
from runtime.protocol_router import ProtocolRouter


class BindingExecutionError(RuntimeErrorBase):
    """Raised when a binding invocation fails."""

    def __init__(
        self, *args: Any, conformance_unmet: bool = False, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self.conformance_unmet = conformance_unmet


_CONFORMANCE_RANK = {
    "experimental": 0,
    "standard": 1,
    "strict": 2,
}


class BindingExecutor:
    """
    Execute a capability through the binding system.

    Pipeline implemented here:

        capability
            ↓
        binding resolution
            ↓
        request construction
            ↓
        protocol routing
            ↓
        service invocation
            ↓
        response mapping
            ↓
        capability output
    """

    def __init__(
        self,
        binding_registry: BindingRegistry,
        binding_resolver: BindingResolver,
        service_resolver: ServiceResolver,
        request_builder: RequestBuilder,
        protocol_router: ProtocolRouter,
        response_mapper: ResponseMapper,
        circuit_breaker_registry: CircuitBreakerRegistry | None = None,
    ) -> None:
        self.binding_registry = binding_registry
        self.binding_resolver = binding_resolver
        self.service_resolver = service_resolver
        self.request_builder = request_builder
        self.protocol_router = protocol_router
        self.response_mapper = response_mapper
        self.circuit_breaker = circuit_breaker_registry or CircuitBreakerRegistry()
        # Resolution plan cache: (capability_id, conformance_override) → plan dict
        self._plan_cache: dict[tuple[str, str | None], dict[str, Any]] = {}
        self._plan_cache_lock = threading.Lock()
        self._plan_cache_max = 256

    def invalidate_plan_cache(self) -> None:
        """Clear cached resolution plans (call after binding activation changes)."""
        with self._plan_cache_lock:
            self._plan_cache.clear()

    def execute(
        self,
        capability,
        step_input: dict,
        trace_callback=None,
        required_conformance_profile: str | None = None,
        cancel_event=None,
    ) -> dict | tuple[dict, dict]:
        """
        Execute a capability using the resolved binding.

        Returns either a plain output mapping or a tuple `(outputs, metadata)`.
        Metadata contains binding/service identifiers useful for tracing.
        """

        capability_id = capability.id
        t0 = time.perf_counter()
        METRICS.inc("binding.execute.total")

        resolution_plan = self.build_resolution_plan(
            capability=capability,
            required_conformance_profile=required_conformance_profile,
        )
        chain = [item["binding_id"] for item in resolution_plan["chain"]]
        required_profile = resolution_plan["required_conformance_profile"]

        attempts: list[dict[str, Any]] = []
        last_error: Exception | None = None
        skipped_for_conformance = 0

        for index, item in enumerate(resolution_plan["chain"]):
            binding_id = item["binding_id"]
            conformance_profile = "standard"

            if not item["eligible"]:
                skipped_for_conformance += 1
                METRICS.inc("binding.conformance_skip")
                attempts.append(
                    {
                        "binding_id": binding_id,
                        "status": "skipped",
                        "conformance_profile": item["conformance_profile"],
                        "required_conformance_profile": required_profile,
                        "skip_reason": item["reason"],
                    }
                )
                continue

            resolved_service_id: str | None = None
            try:
                binding = self.binding_registry.get_binding(binding_id)
                service = self.service_resolver.resolve(binding.service_id)
                resolved_service_id = service.id
                conformance_profile = self._resolve_conformance_profile(
                    binding.metadata
                )

                # Circuit breaker: skip binding if its service circuit is open.
                try:
                    self.circuit_breaker.before_call(service.id)
                except CircuitOpenError:
                    METRICS.inc("binding.circuit_open_skip")
                    attempts.append(
                        {
                            "binding_id": binding_id,
                            "service_id": service.id,
                            "status": "circuit_open",
                            "conformance_profile": conformance_profile,
                        }
                    )
                    continue

                payload = self.request_builder.build(
                    binding=binding,
                    step_input=step_input,
                )

                invocation = InvocationRequest(
                    protocol=binding.protocol,
                    service=service,
                    binding=binding,
                    operation_id=binding.operation_id,
                    payload=payload,
                    context_metadata={
                        "capability_id": capability_id,
                        "binding_id": binding.id,
                        "service_id": service.id,
                    },
                    cancel_event=cancel_event,
                )

                response: InvocationResponse = self.protocol_router.invoke(invocation)

                self.circuit_breaker.record_success(service.id)

                mapped_output = self.response_mapper.map(
                    binding=binding,
                    invocation_response=response,
                )

                attempts.append(
                    {
                        "binding_id": binding.id,
                        "service_id": service.id,
                        "status": "success",
                        "conformance_profile": conformance_profile,
                        "required_conformance_profile": required_profile,
                    }
                )

                elapsed = (time.perf_counter() - t0) * 1000
                METRICS.observe("binding.resolution_ms", elapsed)
                METRICS.inc("binding.execute.success")
                if index > 0:
                    METRICS.inc("binding.execute.fallback_used")
                return mapped_output, {
                    "binding_id": binding.id,
                    "service_id": service.id,
                    "conformance_profile": conformance_profile,
                    "required_conformance_profile": required_profile,
                    "fallback_used": index > 0,
                    "fallback_chain": list(chain),
                    "attempts": attempts,
                    "resolution_plan": resolution_plan,
                    "resolution_ms": round((time.perf_counter() - t0) * 1000, 3),
                }

            except Exception as e:
                last_error = e
                METRICS.inc("binding.execute.fallback")
                if resolved_service_id:
                    self.circuit_breaker.record_failure(resolved_service_id)
                attempts.append(
                    {
                        "binding_id": binding_id,
                        "status": "failed",
                        "conformance_profile": conformance_profile,
                        "required_conformance_profile": required_profile,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    }
                )
                continue

        elapsed = (time.perf_counter() - t0) * 1000
        METRICS.observe("binding.resolution_ms", elapsed)
        METRICS.inc("binding.execute.failed")

        if last_error is not None:
            raise BindingExecutionError(
                (
                    f"Binding execution failed for capability '{capability_id}' after "
                    f"{len(chain)} attempt(s)."
                ),
                capability_id=capability_id,
                cause=last_error,
            ) from last_error

        if skipped_for_conformance > 0:
            raise BindingExecutionError(
                (
                    f"No bindings satisfy required conformance profile '{required_profile}' "
                    f"for capability '{capability_id}'."
                ),
                capability_id=capability_id,
                conformance_unmet=True,
            )

        raise BindingExecutionError(
            f"No executable binding candidates for capability '{capability_id}'.",
            capability_id=capability_id,
        )

    def build_resolution_plan(
        self,
        *,
        capability,
        required_conformance_profile: str | None = None,
    ) -> dict[str, Any]:
        capability_id = capability.id
        cache_key = (capability_id, required_conformance_profile)

        with self._plan_cache_lock:
            cached = self._plan_cache.get(cache_key)
        if cached is not None:
            return cached

        resolved = self.binding_resolver.resolve(capability_id)

        required_profile = self._resolve_required_conformance_profile(
            capability=capability,
            override=required_conformance_profile,
        )

        chain = self._build_fallback_chain(
            capability_id=capability_id,
            primary_binding_id=resolved.binding_id,
        )

        plan_items: list[dict[str, Any]] = []
        for binding_id in chain:
            binding = self.binding_registry.get_binding(binding_id)
            profile = self._resolve_conformance_profile(binding.metadata)
            eligible = self._is_profile_eligible(
                actual_profile=profile,
                required_profile=required_profile,
            )

            reason = "eligible"
            if not eligible:
                reason = (
                    f"profile '{profile}' does not meet required '{required_profile}'"
                )

            plan_items.append(
                {
                    "binding_id": binding.id,
                    "service_id": binding.service_id,
                    "conformance_profile": profile,
                    "eligible": eligible,
                    "reason": reason,
                }
            )

        plan = {
            "capability_id": capability_id,
            "selection_source": resolved.selection_source,
            "primary_binding_id": resolved.binding_id,
            "required_conformance_profile": required_profile,
            "chain": plan_items,
        }

        with self._plan_cache_lock:
            if len(self._plan_cache) < self._plan_cache_max:
                self._plan_cache[cache_key] = plan

        return plan

    def _build_fallback_chain(
        self, *, capability_id: str, primary_binding_id: str
    ) -> list[str]:
        """
        Build deterministic fallback chain:

        1. resolved primary binding
        2. optional binding metadata fallback_binding_id chain
        3. mandatory terminal official default binding
        """
        chain: list[str] = []
        visited: set[str] = set()

        current_id = primary_binding_id
        while current_id and current_id not in visited:
            binding = self.binding_registry.get_binding(current_id)
            if binding.capability_id != capability_id:
                break

            chain.append(current_id)
            visited.add(current_id)

            raw_next = (
                binding.metadata.get("fallback_binding_id")
                if isinstance(binding.metadata, dict)
                else None
            )
            if not isinstance(raw_next, str) or not raw_next:
                break
            current_id = raw_next

        default_binding_id = self.binding_registry.get_official_default_binding_id(
            capability_id
        )
        if (
            isinstance(default_binding_id, str)
            and default_binding_id
            and default_binding_id not in visited
        ):
            chain.append(default_binding_id)

        return chain

    def _resolve_conformance_profile(self, metadata: dict[str, Any] | None) -> str:
        if not isinstance(metadata, dict):
            return "standard"
        profile = metadata.get("conformance_profile")
        if isinstance(profile, str) and profile:
            return profile
        return "standard"

    def _resolve_required_conformance_profile(
        self,
        *,
        capability,
        override: str | None,
    ) -> str:
        candidate = override

        if candidate is None and isinstance(capability.metadata, dict):
            candidate = capability.metadata.get("required_conformance_profile")

        if candidate is None and isinstance(capability.properties, dict):
            candidate = capability.properties.get("required_conformance_profile")

        if candidate is None:
            return "experimental"

        if not isinstance(candidate, str) or not candidate:
            raise BindingExecutionError(
                f"Capability '{capability.id}' has invalid required_conformance_profile.",
                capability_id=capability.id,
            )

        if candidate not in _CONFORMANCE_RANK:
            raise BindingExecutionError(
                (
                    f"Capability '{capability.id}' uses unsupported required_conformance_profile "
                    f"'{candidate}'."
                ),
                capability_id=capability.id,
            )

        return candidate

    def _is_profile_eligible(
        self, *, actual_profile: str, required_profile: str
    ) -> bool:
        return _CONFORMANCE_RANK[actual_profile] >= _CONFORMANCE_RANK[required_profile]
