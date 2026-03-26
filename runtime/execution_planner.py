from __future__ import annotations

from typing import Iterable

from runtime.errors import InvalidSkillSpecError
from runtime.models import SkillSpec, StepSpec


def validate_consumes_chain(
    steps: tuple[StepSpec, ...],
    capability_loader,
) -> list[str]:
    """
    Check that each step's capability consumes types that upstream steps produce.

    Returns a list of warning strings (empty when the chain is satisfied).
    Only inspects steps backed by capabilities with cognitive_hints.
    """
    warnings: list[str] = []
    produced_types: set[str] = set()

    for step in steps:
        if step.uses.startswith("skill:"):
            continue
        try:
            cap = capability_loader.get_capability(step.uses)
        except Exception:
            continue
        hints = getattr(cap, "cognitive_hints", None)
        if not hints or not isinstance(hints, dict):
            continue

        consumes = hints.get("consumes")
        if isinstance(consumes, list):
            for t in consumes:
                if isinstance(t, str) and t not in produced_types:
                    warnings.append(
                        f"Step '{step.id}' (capability {step.uses}) consumes type "
                        f"'{t}' which has not been produced by any upstream step."
                    )

        produces = hints.get("produces")
        if isinstance(produces, dict):
            for field_spec in produces.values():
                if isinstance(field_spec, dict) and isinstance(
                    field_spec.get("type"), str
                ):
                    produced_types.add(field_spec["type"])

    return warnings


class ExecutionPlanner:
    """
    Produces the ordered execution plan for a skill.

    In v1 the planner is intentionally simple:
    - steps execute strictly in the order declared
    - validation focuses on structural correctness
    - no DAG or parallelism yet
    """

    def build_plan(self, skill: SkillSpec) -> tuple[StepSpec, ...]:
        """
        Validate the skill structure and return the ordered step plan.
        """
        self._validate_skill(skill)
        return skill.steps

    def _validate_skill(self, skill: SkillSpec) -> None:
        """
        Perform structural validation before execution begins.

        This protects the engine from running partially invalid skills.
        """
        if not skill.steps:
            raise InvalidSkillSpecError(
                f"Skill '{skill.id}' defines no steps.",
                skill_id=skill.id,
            )

        self._validate_unique_step_ids(skill.steps, skill.id)
        self._validate_step_targets(skill)

    def _validate_unique_step_ids(
        self,
        steps: Iterable[StepSpec],
        skill_id: str,
    ) -> None:
        seen: set[str] = set()

        for step in steps:
            if step.id in seen:
                raise InvalidSkillSpecError(
                    f"Skill '{skill_id}' contains duplicate step id '{step.id}'.",
                    skill_id=skill_id,
                )
            seen.add(step.id)

    def _validate_step_targets(self, skill: SkillSpec) -> None:
        """
        Validate that output mappings target valid writable namespaces.

        Writable:  vars, outputs, working, output, extensions
        Read-only: inputs, frame, trace
        """
        writable = {"vars", "outputs", "working", "output", "extensions"}
        read_only = {"inputs", "frame", "trace"}

        for step in skill.steps:
            for produced_field, target in step.output_mapping.items():
                if not isinstance(target, str) or "." not in target:
                    raise InvalidSkillSpecError(
                        f"Step '{step.id}' has invalid output target '{target}'.",
                        skill_id=skill.id,
                    )

                namespace, _ = target.split(".", 1)

                if namespace in read_only:
                    raise InvalidSkillSpecError(
                        f"Step '{step.id}' writes to read-only namespace '{namespace}'.",
                        skill_id=skill.id,
                    )

                if namespace not in writable:
                    raise InvalidSkillSpecError(
                        f"Step '{step.id}' writes to unsupported namespace '{namespace}'.",
                        skill_id=skill.id,
                    )
