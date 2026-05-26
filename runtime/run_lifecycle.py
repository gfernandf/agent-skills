from __future__ import annotations

from dataclasses import dataclass


RUN_STATUS_PENDING = "pending"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_WAITING_FOR_HUMAN = "waiting_for_human"
RUN_STATUS_WAITING_FOR_SIGNAL = "waiting_for_signal"
RUN_STATUS_REPLAYING = "replaying"
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_CANCELED = "canceled"

RUN_STATUSES = {
    RUN_STATUS_PENDING,
    RUN_STATUS_RUNNING,
    RUN_STATUS_WAITING_FOR_HUMAN,
    RUN_STATUS_WAITING_FOR_SIGNAL,
    RUN_STATUS_REPLAYING,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_CANCELED,
}

TERMINAL_RUN_STATUSES = {
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_CANCELED,
}

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    RUN_STATUS_PENDING: {RUN_STATUS_RUNNING},
    RUN_STATUS_RUNNING: {
        RUN_STATUS_WAITING_FOR_HUMAN,
        RUN_STATUS_WAITING_FOR_SIGNAL,
        RUN_STATUS_REPLAYING,
        RUN_STATUS_COMPLETED,
        RUN_STATUS_FAILED,
        RUN_STATUS_CANCELED,
    },
    RUN_STATUS_WAITING_FOR_HUMAN: {RUN_STATUS_RUNNING, RUN_STATUS_CANCELED},
    RUN_STATUS_WAITING_FOR_SIGNAL: {RUN_STATUS_RUNNING, RUN_STATUS_CANCELED},
    RUN_STATUS_REPLAYING: {
        RUN_STATUS_RUNNING,
        RUN_STATUS_FAILED,
        RUN_STATUS_CANCELED,
    },
    RUN_STATUS_COMPLETED: set(),
    RUN_STATUS_FAILED: set(),
    RUN_STATUS_CANCELED: set(),
}


@dataclass(frozen=True)
class RunTransitionResult:
    allowed: bool
    reason: str | None = None


class RunStateMachine:
    """Validate canonical run status transitions."""

    def is_valid_status(self, status: str) -> bool:
        return status in RUN_STATUSES

    def can_transition(self, from_status: str, to_status: str) -> RunTransitionResult:
        if from_status not in RUN_STATUSES:
            return RunTransitionResult(False, f"Unknown from_status '{from_status}'.")
        if to_status not in RUN_STATUSES:
            return RunTransitionResult(False, f"Unknown to_status '{to_status}'.")
        if from_status == to_status:
            return RunTransitionResult(True, None)

        allowed_targets = _ALLOWED_TRANSITIONS.get(from_status, set())
        if to_status not in allowed_targets:
            return RunTransitionResult(
                False,
                f"Transition {from_status} -> {to_status} is not allowed.",
            )
        return RunTransitionResult(True, None)

    def ensure_transition(self, from_status: str, to_status: str) -> None:
        result = self.can_transition(from_status, to_status)
        if not result.allowed:
            raise ValueError(result.reason or "Invalid run status transition.")
