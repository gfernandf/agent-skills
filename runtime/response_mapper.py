from __future__ import annotations

from typing import Any

from runtime.binding_models import BindingSpec, InvocationResponse
from runtime.errors import RuntimeErrorBase


class ResponseMappingError(RuntimeErrorBase):
    """Raised when a binding response cannot be mapped into capability outputs."""


class ResponseMapper:
    """
    Map a protocol-agnostic invocation response into capability outputs.

    Binding response mappings operate on the invocation response using the namespace:

        response.<field-path>

    Example:
        response:
          summary: response.data.summary
          metadata: response.metadata

    Rules in v1:
    - every declared output mapping must resolve successfully
    - only the 'response.' namespace is interpreted as a response reference
    - non-reference strings are treated as literals
    - dict/list structures are not expected in response mappings v1; each output
      maps to one string reference
    """

    def map(
        self,
        binding: BindingSpec,
        invocation_response: InvocationResponse,
    ) -> dict[str, Any]:
        raw_response = invocation_response.raw_response

        if not isinstance(binding.response_mapping, dict):
            raise ResponseMappingError(
                f"Binding '{binding.id}' has an invalid response mapping.",
                capability_id=binding.capability_id,
            )

        mapped: dict[str, Any] = {}

        for output_name, response_ref in binding.response_mapping.items():
            if not isinstance(output_name, str) or not output_name:
                raise ResponseMappingError(
                    f"Binding '{binding.id}' contains an invalid output name in response mapping.",
                    capability_id=binding.capability_id,
                )

            if not isinstance(response_ref, str) or not response_ref:
                raise ResponseMappingError(
                    f"Binding '{binding.id}' response mapping for '{output_name}' must be a non-empty string.",
                    capability_id=binding.capability_id,
                )

            mapped[output_name] = self._resolve_response_reference(
                response_ref,
                raw_response=raw_response,
                binding=binding,
            )

        return mapped

    def _resolve_response_reference(
        self,
        value: str,
        *,
        raw_response: Any,
        binding: BindingSpec,
    ) -> Any:
        if "." not in value:
            return value

        namespace, field_path = value.split(".", 1)

        if namespace != "response":
            return value

        if not field_path:
            raise ResponseMappingError(
                f"Binding '{binding.id}' contains an invalid response reference '{value}'.",
                capability_id=binding.capability_id,
            )

        return self._resolve_response_path(
            field_path,
            raw_response=raw_response,
            binding=binding,
        )

    def _resolve_response_path(
        self,
        field_path: str,
        *,
        raw_response: Any,
        binding: BindingSpec,
    ) -> Any:
        current: Any = raw_response

        for part in field_path.split("."):
            if not part:
                raise ResponseMappingError(
                    f"Binding '{binding.id}' contains an invalid response path 'response.{field_path}'.",
                    capability_id=binding.capability_id,
                )

            if isinstance(current, dict):
                if part not in current:
                    raise ResponseMappingError(
                        f"Binding '{binding.id}' references missing response field 'response.{field_path}'.",
                        capability_id=binding.capability_id,
                    )
                current = current[part]
                continue

            raise ResponseMappingError(
                f"Binding '{binding.id}' cannot resolve 'response.{field_path}' because '{part}' is accessed on a non-mapping value.",
                capability_id=binding.capability_id,
            )

        return current