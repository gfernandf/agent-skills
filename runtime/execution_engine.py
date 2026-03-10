from __future__ import annotations

from runtime.errors import (
    FinalOutputValidationError,
    StepExecutionError,
)
from runtime.execution_state import (
    create_execution_state,
    emit_event,
    mark_finished,
    mark_started,
    record_step_result,
)
from runtime.input_mapper import build_step_input
from runtime.models import (
    ExecutionContext,
    ExecutionRequest,
    SkillExecutionResult,
    StepResult,
)
from runtime.output_mapper import apply_step_output


class ExecutionEngine:
    """
    Core runtime engine responsible for executing a skill.

    Responsibilities:
    - load skill
    - build execution plan
    - resolve step inputs
    - execute capabilities or nested skills
    - apply step outputs
    - validate final outputs
    """

    def __init__(
        self,
        skill_loader,
        capability_loader,
        execution_planner,
        reference_resolver,
        capability_executor,
        nested_skill_runner,
    ) -> None:
        self.skill_loader = skill_loader
        self.capability_loader = capability_loader
        self.execution_planner = execution_planner
        self.reference_resolver = reference_resolver
        self.capability_executor = capability_executor
        self.nested_skill_runner = nested_skill_runner

    def execute(
        self,
        request: ExecutionRequest,
        parent_context: ExecutionContext | None = None,
        trace_callback=None,
    ) -> SkillExecutionResult:
        """
        Execute a skill and return the final result.
        """
        skill = self.skill_loader.get_skill(request.skill_id)

        state = create_execution_state(skill.id, request.inputs)

        context = ExecutionContext(
            state=state,
            options=request.options,
            depth=(parent_context.depth + 1) if parent_context else 0,
            parent_skill_id=parent_context.state.skill_id if parent_context else None,
            lineage=(
                (*parent_context.lineage, skill.id)
                if parent_context
                else (skill.id,)
            ),
        )

        mark_started(state)

        emit_event(
            state,
            "skill_start",
            f"Executing skill '{skill.id}'.",
        )

        if trace_callback:
            trace_callback(state.events[-1])

        plan = self.execution_planner.build_plan(skill)

        for step in plan:
            result = self._execute_step(step, skill.id, context, trace_callback)
            record_step_result(state, result)

            if result.status != "completed":
                 if context.options.fail_fast:
                     mark_finished(state, "failed")
                     raise StepExecutionError(
                         f"Step '{step.id}' failed: {result.error_message}",
                         skill_id=skill.id,
                         step_id=step.id,
                    )

        self._validate_final_outputs(skill, state)

        mark_finished(state, "completed")

        emit_event(
            state,
            "skill_completed",
            f"Skill '{skill.id}' completed.",
        )

        if trace_callback:
            trace_callback(state.events[-1])

        return SkillExecutionResult(
            skill_id=skill.id,
            status=state.status,
            outputs=dict(state.outputs),
            state=state,
        )

    def _execute_step(
        self,
        step,
        skill_id: str,
        context: ExecutionContext,
        trace_callback=None,
    ) -> StepResult:
        state = context.state

        emit_event(
            state,
            "step_start",
            f"Starting step '{step.id}'.",
            step_id=step.id,
        )

        if trace_callback:
            trace_callback(state.events[-1])

        try:
            step_input = build_step_input(
                step,
                state,
                self.reference_resolver,
            )

            if step.uses.startswith("skill:"):
                produced = self.nested_skill_runner.execute(
                    step.uses,
                    step_input,
                    context,
                )
            else:
                capability = self.capability_loader.get_capability(step.uses)

                produced = self.capability_executor.execute(
                    capability,
                    step_input,
                )

            apply_step_output(
                step,
                produced,
                state,
            )

            emit_event(
                state,
                "step_completed",
                f"Step '{step.id}' completed.",
                step_id=step.id,
            )

            return StepResult(
                step_id=step.id,
                uses=step.uses,
                status="completed",
                resolved_input=step_input,
                produced_output=produced,
            )

        except Exception as e:
            emit_event(
                state,
                "step_failed",
                f"Step '{step.id}' failed.",
                step_id=step.id,
                data={"error": str(e)},
            )

            return StepResult(
                step_id=step.id,
                uses=step.uses,
                status="failed",
                resolved_input={},
                produced_output=None,
                error_message=str(e),
            )

    def _validate_final_outputs(self, skill, state) -> None:
        """
        Ensure all required skill outputs have been produced.
        """
        for name, spec in skill.outputs.items():
            if spec.required and name not in state.outputs:
                raise FinalOutputValidationError(
                    f"Required output '{name}' not produced.",
                    skill_id=skill.id,
                )