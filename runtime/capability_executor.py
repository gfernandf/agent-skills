from __future__ import annotations

from typing import Any, Protocol

from runtime.errors import CapabilityExecutionError, CapabilityNotFoundError
from runtime.models import CapabilitySpec


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
    ) -> dict[str, Any]:
        """
        Execute a capability and return its outputs.

        Must return a mapping whose keys correspond to the capability outputs.
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
    ) -> dict[str, Any]:
        try:
            result = self.binding_executor.execute(capability, step_input)
        except CapabilityNotFoundError:
            raise
        except Exception as e:
            raise CapabilityExecutionError(
                f"Capability '{capability.id}' execution failed.",
                capability_id=capability.id,
                cause=e,
            ) from e

        if not isinstance(result, dict):
            raise CapabilityExecutionError(
                f"Capability '{capability.id}' returned a non-mapping result.",
                capability_id=capability.id,
            )

        return result