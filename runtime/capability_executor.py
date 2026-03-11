from __future__ import annotations

import time
from typing import Any, Protocol

from runtime.errors import CapabilityExecutionError, CapabilityNotFoundError
from runtime.models import CapabilitySpec
from runtime.observability import elapsed_ms, log_event


class CapabilityExecutor(Protocol):
    """
    Interface implemented by the binding layer.

    The core runtime engine does NOT know how capabilities are implemented.
    It only delegates execution to this abstraction.
    """

    def execute(
        self,
        capability: CapabilitySpec,
        step_input: dict[str, Any],
        trace_callback=None,
    ) -> dict[str, Any] | tuple[dict[str, Any], dict[str, Any]]:
        """
        Execute a capability and return its outputs.

        May also return a `(outputs, metadata)` tuple when additional
        binding/service information is available. Metadata should be a
        dictionary containing any keys that may be useful for tracing.
        """
        ...


class DefaultCapabilityExecutor:
    """
    Default runtime adapter that delegates capability execution to the binding layer.

    This class bridges the core runtime with the binding system implemented later
    in the project (BindingResolver + BindingExecutor).
    """

    def __init__(self, binding_executor) -> None:
        self.binding_executor = binding_executor

    def execute(
        self,
        capability: CapabilitySpec,
        step_input: dict[str, Any],
        trace_callback=None,
    ) -> dict[str, Any] | tuple[dict[str, Any], dict[str, Any]]:
        start_time = time.perf_counter()
        log_event(
            "capability.execute.start",
            capability_id=capability.id,
            input_keys=sorted(step_input.keys()),
        )
        try:
            result = self.binding_executor.execute(capability, step_input, trace_callback=trace_callback)
        except CapabilityNotFoundError:
            log_event(
                "capability.execute.failed",
                level="error",
                capability_id=capability.id,
                duration_ms=elapsed_ms(start_time),
                error_type="CapabilityNotFoundError",
            )
            raise
        except Exception as e:
            log_event(
                "capability.execute.failed",
                level="error",
                capability_id=capability.id,
                duration_ms=elapsed_ms(start_time),
                error_type=type(e).__name__,
                error_message=str(e),
            )
            raise CapabilityExecutionError(
                f"Capability '{capability.id}' execution failed.",
                capability_id=capability.id,
                cause=e,
            ) from e

        # `result` may be a tuple from BindingExecutor
        if isinstance(result, tuple):
            outputs, meta = result
        else:
            outputs, meta = result, {}

        if not isinstance(outputs, dict):
            log_event(
                "capability.execute.failed",
                level="error",
                capability_id=capability.id,
                duration_ms=elapsed_ms(start_time),
                error_type="InvalidOutputType",
                output_type=type(outputs).__name__,
            )
            raise CapabilityExecutionError(
                f"Capability '{capability.id}' returned a non-mapping result.",
                capability_id=capability.id,
            )

        log_event(
            "capability.execute.completed",
            capability_id=capability.id,
            duration_ms=elapsed_ms(start_time),
            output_keys=sorted(outputs.keys()),
            binding_id=(meta.get("binding_id") if isinstance(meta, dict) else None),
            service_id=(meta.get("service_id") if isinstance(meta, dict) else None),
        )

        # attach metadata into return if present
        if meta:
            return outputs, meta
        return outputs