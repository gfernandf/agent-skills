from __future__ import annotations

from typing import Iterable

from runtime.errors import InvalidSkillSpecError
from runtime.models import SkillSpec, StepSpec


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
        Validate that output mappings target valid namespaces.

        v1 rule set:
        - vars.<name>
        - outputs.<name>
        """
        for step in skill.steps:
            for produced_field, target in step.output_mapping.items():
                if not isinstance(target, str) or "." not in target:
                    raise InvalidSkillSpecError(
                        f"Step '{step.id}' has invalid output target '{target}'.",
                        skill_id=skill.id,
                    )

                namespace, _ = target.split(".", 1)

                if namespace not in {"vars", "outputs"}:
                    raise InvalidSkillSpecError(
                        f"Step '{step.id}' writes to unsupported namespace '{namespace}'.",
                        skill_id=skill.id,
                    )