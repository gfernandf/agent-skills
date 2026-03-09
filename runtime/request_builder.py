from __future__ import annotations

from typing import Any

from runtime.binding_models import BindingSpec
from runtime.errors import RuntimeErrorBase


class RequestBuildError(RuntimeErrorBase):
    """Raised when a binding request payload cannot be constructed."""


class RequestBuilder:
    """
    Build the concrete invocation payload for a binding.

    Binding request templates operate on the already-resolved step input, using
    the namespace:

        input.<field>

    Examples:
        request:
          text: input.text
          options:
            max_length: input.max_length

    Rules in v1:
    - literals are preserved
    - dict/list structures are resolved recursively
    - only the 'input.' namespace is supported here
    """

    def build(
        self,
        binding: BindingSpec,
        step_input: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(step_input, dict):
            raise RequestBuildError(
                f"Step input for binding '{binding.id}' must be a mapping."
            )

        try:
            payload = self._resolve_value(
                binding.request_template,
                step_input=step_input,
                binding=binding,
            )
        except RequestBuildError:
            raise
        except Exception as e:
            raise RequestBuildError(
                f"Failed to build request payload for binding '{binding.id}'.",
                capability_id=binding.capability_id,
                cause=e,
            ) from e

        if not isinstance(payload, dict):
            raise RequestBuildError(
                f"Binding '{binding.id}' request template must resolve to a mapping.",
                capability_id=binding.capability_id,
            )

        return payload

    def _resolve_value(
        self,
        value: Any,
        *,
        step_input: dict[str, Any],
        binding: BindingSpec,
    ) -> Any:
        if isinstance(value, dict):
            resolved: dict[str, Any] = {}
            for key, nested_value in value.items():
                if not isinstance(key, str) or not key:
                    raise RequestBuildError(
                        f"Binding '{binding.id}' request template contains an invalid key.",
                        capability_id=binding.capability_id,
                    )
                resolved[key] = self._resolve_value(
                    nested_value,
                    step_input=step_input,
                    binding=binding,
                )
            return resolved

        if isinstance(value, list):
            return [
                self._resolve_value(
                    item,
                    step_input=step_input,
                    binding=binding,
                )
                for item in value
            ]

        if isinstance(value, str):
            return self._resolve_string_reference(
                value,
                step_input=step_input,
                binding=binding,
            )

        return value

    def _resolve_string_reference(
        self,
        value: str,
        *,
        step_input: dict[str, Any],
        binding: BindingSpec,
    ) -> Any:
        if "." not in value:
            return value

        namespace, field_path = value.split(".", 1)

        if namespace != "input":
            return value

        if not field_path:
            raise RequestBuildError(
                f"Binding '{binding.id}' contains an invalid input reference '{value}'.",
                capability_id=binding.capability_id,
            )

        return self._resolve_input_path(
            field_path,
            step_input=step_input,
            binding=binding,
        )

    def _resolve_input_path(
        self,
        field_path: str,
        *,
        step_input: dict[str, Any],
        binding: BindingSpec,
    ) -> Any:
        current: Any = step_input

        for part in field_path.split("."):
            if not part:
                raise RequestBuildError(
                    f"Binding '{binding.id}' contains an invalid input path 'input.{field_path}'.",
                    capability_id=binding.capability_id,
                )

            if not isinstance(current, dict):
                raise RequestBuildError(
                    f"Binding '{binding.id}' cannot resolve 'input.{field_path}' because '{part}' is accessed on a non-mapping value.",
                    capability_id=binding.capability_id,
                )

            if part not in current:
                raise RequestBuildError(
                    f"Binding '{binding.id}' references missing input field 'input.{field_path}'.",
                    capability_id=binding.capability_id,
                )

            current = current[part]

        return current