from __future__ import annotations

from typing import Any

from runtime.errors import (
    MaxSkillDepthExceededError,
    NestedSkillExecutionError,
    SkillNotFoundError,
)
from runtime.models import (
    ExecutionContext,
    ExecutionOptions,
    ExecutionRequest,
    SkillExecutionResult,
)


class NestedSkillRunner:
    """
    Executes nested skills referenced by steps using the syntax:

        uses: "skill:<skill-id>"

    This component delegates the actual execution to the same ExecutionEngine,
    allowing recursive skill composition.
    """

    def __init__(self, execution_engine) -> None:
        self.execution_engine = execution_engine

    def execute(
        self,
        skill_reference: str,
        step_input: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """
        Execute a nested skill and return its outputs.
        """
        skill_id = self._parse_skill_reference(skill_reference)

        self._check_depth(context)

        request = ExecutionRequest(
            skill_id=skill_id,
            inputs=step_input,
            options=context.options,
            trace_id=context.trace_id,
        )

        try:
            result: SkillExecutionResult = self.execution_engine.execute(
                request,
                parent_context=context,
            )
        except SkillNotFoundError:
            raise
        except Exception as e:
            raise NestedSkillExecutionError(
                f"Nested skill '{skill_id}' execution failed.",
                skill_id=skill_id,
                cause=e,
            ) from e

        if result.status != "completed":
            raise NestedSkillExecutionError(
                f"Nested skill '{skill_id}' did not complete successfully.",
                skill_id=skill_id,
            )

        return result.outputs

    def _parse_skill_reference(self, reference: str) -> str:
        """
        Extract the skill id from a reference like:

            skill:<skill-id>
        """
        prefix = "skill:"

        if not isinstance(reference, str) or not reference.startswith(prefix):
            raise NestedSkillExecutionError(
                f"Invalid nested skill reference '{reference}'."
            )

        skill_id = reference[len(prefix):].strip()

        if not skill_id:
            raise NestedSkillExecutionError(
                f"Nested skill reference '{reference}' has no skill id."
            )

        return skill_id

    def _check_depth(self, context: ExecutionContext) -> None:
        """
        Prevent infinite recursion or excessively deep skill graphs.
        """
        options: ExecutionOptions = context.options

        if context.depth + 1 > options.max_skill_depth:
            raise MaxSkillDepthExceededError(
                f"Maximum skill depth ({options.max_skill_depth}) exceeded.",
                skill_id=context.state.skill_id,
            )