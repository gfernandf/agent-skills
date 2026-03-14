from __future__ import annotations

from pathlib import Path
from typing import Sequence

from runtime.errors import SkillNotFoundError
from runtime.models import SkillSpec
from runtime.skill_loader import SkillLoader, YamlSkillLoader


class CompositeSkillLoader:
    """
    Merges skills from multiple roots, in priority order.

    The first root that defines a skill_id wins.  This lets a local
    ``skills/local/`` directory override or supplement the shared registry.

    Typical wiring:

        CompositeSkillLoader([
            YamlSkillLoader(local_skills_root),   # highest priority
            YamlSkillLoader(registry_root),        # shared registry
        ])
    """

    def __init__(self, loaders: Sequence[SkillLoader]) -> None:
        if not loaders:
            raise ValueError("CompositeSkillLoader requires at least one loader.")
        self._loaders = list(loaders)

    def get_skill(self, skill_id: str) -> SkillSpec:
        last_exc: Exception | None = None
        for loader in self._loaders:
            try:
                return loader.get_skill(skill_id)
            except SkillNotFoundError as exc:
                last_exc = exc
                continue
        raise SkillNotFoundError(
            f"Skill '{skill_id}' not found in any registered root.",
            skill_id=skill_id,
            cause=last_exc,
        ) from last_exc

    def list_all_ids(self) -> list[str]:
        """Return the de-duplicated union of skill ids across all loaders (priority order)."""
        seen: set[str] = set()
        result: list[str] = []
        for loader in self._loaders:
            if isinstance(loader, YamlSkillLoader):
                loader._skill_index  # trigger lazy build if needed
                if loader._skill_index is not None:
                    for skill_id in loader._skill_index:
                        if skill_id not in seen:
                            seen.add(skill_id)
                            result.append(skill_id)
        return result
