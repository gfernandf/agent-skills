from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class SkillSummary:
    skill_id: str
    name: str
    description: str
    domain: str | None
    channel: str | None
    status: str | None
    role: str | None
    invocation: str | None
    effect_mode: str | None
    tags: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "domain": self.domain,
            "channel": self.channel,
            "status": self.status,
            "role": self.role,
            "invocation": self.invocation,
            "effect_mode": self.effect_mode,
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class DiscoverResult:
    skill: SkillSummary
    score: float
    reason: str
    reason_codes: tuple[str, ...] = ()
    score_breakdown: dict[str, float] | None = None
    evidence: dict[str, float | str | None] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = self.skill.to_dict()
        payload["score"] = self.score
        payload["reason"] = self.reason
        payload["reason_codes"] = list(self.reason_codes)
        payload["score_breakdown"] = self.score_breakdown or {}
        payload["evidence"] = self.evidence or {}
        return payload


@dataclass(frozen=True)
class AttachResult:
    skill_id: str
    target_type: str
    target_ref: str
    execution: dict[str, Any]
    attached_at: str
    attach_context: dict[str, Any] | None = None

    @classmethod
    def now(
        cls,
        *,
        skill_id: str,
        target_type: str,
        target_ref: str,
        execution: dict[str, Any],
        attach_context: dict[str, Any] | None = None,
    ) -> "AttachResult":
        return cls(
            skill_id=skill_id,
            target_type=target_type,
            target_ref=target_ref,
            execution=execution,
            attached_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            attach_context=attach_context,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "skill_id": self.skill_id,
            "target_type": self.target_type,
            "target_ref": self.target_ref,
            "execution": self.execution,
            "attached_at": self.attached_at,
        }
        if isinstance(self.attach_context, dict):
            payload["attach_context"] = self.attach_context
        return payload
