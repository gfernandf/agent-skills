from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from gateway.models import DiscoverResult, SkillSummary


_READ_ONLY_HINTS = {
    "read",
    "lookup",
    "find",
    "list",
    "inspect",
    "classify",
    "extract",
}


@dataclass(frozen=True)
class DiscoveryQuery:
    intent: str
    domain: str | None = None
    role_filter: str | None = None
    limit: int = 10


def rank_skills(
    skills: Iterable[SkillSummary],
    query: DiscoveryQuery,
    *,
    evidence: dict[str, dict[str, float | str | None]] | None = None,
) -> list[DiscoverResult]:
    return rank_skills_with_evidence(skills, query, evidence=evidence or {})


def rank_skills_with_evidence(
    skills: Iterable[SkillSummary],
    query: DiscoveryQuery,
    *,
    evidence: dict[str, dict[str, float | str | None]],
) -> list[DiscoverResult]:
    tokens = _tokenize(query.intent)
    prefer_read_only = bool(tokens.intersection(_READ_ONLY_HINTS))

    ranked: list[DiscoverResult] = []
    for skill in skills:
        if query.domain and (skill.domain or "") != query.domain:
            continue
        if query.role_filter and (skill.role or "") != query.role_filter:
            continue

        score = 0.0
        reasons: list[str] = []
        reason_codes: list[str] = []
        score_breakdown: dict[str, float] = {}

        def _add_component(code: str, value: float, reason: str) -> None:
            nonlocal score
            score += value
            score_breakdown[code] = round(value, 4)
            reason_codes.append(code)
            reasons.append(reason)

        if skill.role == "procedure":
            _add_component("role_procedure", 0.35, "role=procedure")
        elif skill.role == "utility":
            _add_component("role_utility", 0.20, "role=utility")
        elif skill.role == "sidecar":
            _add_component("role_sidecar", 0.05, "role=sidecar")

        if (skill.status or "") == "stable":
            _add_component("status_stable", 0.20, "status=stable")
        elif (skill.status or "") == "experimental":
            _add_component("status_experimental", 0.05, "status=experimental")

        text = " ".join(
            [
                skill.skill_id,
                skill.name,
                skill.description,
                " ".join(skill.tags),
                skill.domain or "",
            ]
        ).lower()

        overlap = len({t for t in tokens if t in text})
        if overlap > 0:
            lexical = min(0.35, overlap * 0.08)
            _add_component("lexical_match", lexical, f"lexical_match={overlap}")

        if prefer_read_only and skill.effect_mode == "read_only":
            _add_component("read_only_match", 0.10, "read_only_match")

        if skill.invocation in {"attach", "both"}:
            _add_component("attach_penalty", -0.03, "attach_penalty")

        ev = evidence.get(skill.skill_id, {})
        exec_30d = ev.get("executions_30d")
        if isinstance(exec_30d, (int, float)) and exec_30d > 0:
            usage_bonus = min(0.12, float(exec_30d) / 100.0)
            _add_component("usage_30d", usage_bonus, f"usage_30d={int(exec_30d)}")

        successes_30d = ev.get("successes_30d")
        if (
            isinstance(exec_30d, (int, float))
            and isinstance(successes_30d, (int, float))
            and exec_30d > 0
        ):
            success_rate = float(successes_30d) / float(exec_30d)
            if success_rate >= 0.9:
                _add_component("success_rate_high", 0.08, "success_rate_high")
            elif success_rate >= 0.75:
                _add_component("success_rate_medium", 0.04, "success_rate_medium")

        lifecycle = ev.get("lifecycle_state")
        if lifecycle == "recommended":
            _add_component("lifecycle_recommended", 0.10, "lifecycle=recommended")
        elif lifecycle == "trusted":
            _add_component("lifecycle_trusted", 0.07, "lifecycle=trusted")
        elif lifecycle == "lab-verified":
            _add_component("lifecycle_lab_verified", 0.05, "lifecycle=lab-verified")

        overall = ev.get("overall_score")
        if isinstance(overall, (int, float)):
            overall_bonus = min(0.10, max(0.0, float(overall) / 1000.0))
            _add_component(
                "overall_score",
                overall_bonus,
                f"overall_score={round(float(overall), 1)}",
            )

        ranked.append(
            DiscoverResult(
                skill=skill,
                score=round(max(score, 0.0), 4),
                reason=", ".join(reasons) if reasons else "default_rank",
                reason_codes=tuple(reason_codes),
                score_breakdown=score_breakdown,
                evidence={
                    "executions_30d": ev.get("executions_30d"),
                    "successes_30d": ev.get("successes_30d"),
                    "p95_duration_ms": ev.get("p95_duration_ms"),
                    "lifecycle_state": ev.get("lifecycle_state"),
                    "overall_score": ev.get("overall_score"),
                },
            )
        )

    ranked.sort(key=lambda item: (-item.score, item.skill.skill_id))

    limit = max(1, int(query.limit))
    return ranked[:limit]


def _tokenize(text: str) -> set[str]:
    cleaned = "".join(ch.lower() if (ch.isalnum() or ch == " ") else " " for ch in text)
    return {t for t in cleaned.split() if len(t) >= 2}


# ── P4 — Inverted Index for O(1) token-based skill lookup ──────────────


class SkillSearchIndex:
    """Pre-built inverted index that maps tokens → skill IDs.

    With 1000+ skills, linear-scanning all skills per discovery request
    becomes expensive.  This index allows O(k) lookup where k is the
    number of intent tokens.
    """

    def __init__(self) -> None:
        self._token_to_skills: dict[str, set[str]] = {}
        self._skills: dict[str, "SkillSummary"] = {}

    def build(self, skills: Iterable["SkillSummary"]) -> None:
        """Rebuild the full index from a skill collection."""
        self._token_to_skills.clear()
        self._skills.clear()
        for skill in skills:
            self._skills[skill.skill_id] = skill
            text = " ".join(
                [
                    skill.skill_id,
                    skill.name,
                    skill.description,
                    " ".join(skill.tags),
                    skill.domain or "",
                ]
            )
            for token in _tokenize(text):
                self._token_to_skills.setdefault(token, set()).add(skill.skill_id)

    def candidates(self, intent_tokens: set[str]) -> list["SkillSummary"]:
        """Return skills that match at least one intent token."""
        ids: set[str] = set()
        for token in intent_tokens:
            ids.update(self._token_to_skills.get(token, set()))
        return [self._skills[sid] for sid in ids if sid in self._skills]

    @property
    def size(self) -> int:
        return len(self._skills)
