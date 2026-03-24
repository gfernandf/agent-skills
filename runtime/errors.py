from __future__ import annotations


class RuntimeErrorBase(Exception):
    """
    Base exception for all runtime-level errors.

    Carries optional execution context so higher layers (CLI, tracing, tooling)
    can present precise diagnostics without guessing where a failure happened.
    """

    def __init__(
        self,
        message: str,
        *,
        skill_id: str | None = None,
        step_id: str | None = None,
        capability_id: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.skill_id = skill_id
        self.step_id = step_id
        self.capability_id = capability_id
        self.cause = cause

    def __str__(self) -> str:
        parts: list[str] = [self.message]

        context: list[str] = []
        if self.skill_id:
            context.append(f"skill={self.skill_id}")
        if self.step_id:
            context.append(f"step={self.step_id}")
        if self.capability_id:
            context.append(f"capability={self.capability_id}")

        if context:
            parts.append(f"[{', '.join(context)}]")

        if self.cause is not None:
            parts.append(f"(cause: {self.cause})")

        return " ".join(parts)


class SkillNotFoundError(RuntimeErrorBase):
    """Raised when a requested skill cannot be found."""


class CapabilityNotFoundError(RuntimeErrorBase):
    """Raised when a requested capability cannot be found."""


class InvalidSkillSpecError(RuntimeErrorBase):
    """Raised when a skill source file cannot be normalized into a valid SkillSpec."""


class InvalidCapabilitySpecError(RuntimeErrorBase):
    """Raised when a capability source file cannot be normalized into a valid CapabilitySpec."""


class ReferenceResolutionError(RuntimeErrorBase):
    """Raised when the runtime cannot resolve a reference like inputs.*, vars.* or outputs.*."""


class InputMappingError(RuntimeErrorBase):
    """Raised when a step input mapping cannot be resolved into a valid runtime payload."""


class OutputMappingError(RuntimeErrorBase):
    """Raised when a step output cannot be written into runtime targets."""


class StepExecutionError(RuntimeErrorBase):
    """Raised when a step fails during execution orchestration."""


class CapabilityExecutionError(RuntimeErrorBase):
    """Raised when capability execution fails below the engine boundary."""


class NestedSkillExecutionError(RuntimeErrorBase):
    """Raised when a nested skill execution fails."""


class FinalOutputValidationError(RuntimeErrorBase):
    """Raised when required final outputs are missing after skill execution."""


class MaxSkillDepthExceededError(RuntimeErrorBase):
    """Raised when nested skill execution exceeds the configured maximum depth."""


class InvalidExecutionOptionsError(RuntimeErrorBase):
    """Raised when execution options are invalid."""


class AttachValidationError(RuntimeErrorBase):
    """Raised when a requested attach operation violates skill classification rules."""


class SafetyTrustLevelError(RuntimeErrorBase):
    """Raised when a capability requires a higher trust level than the execution context provides."""


class SafetyGateFailedError(RuntimeErrorBase):
    """Raised when a mandatory safety gate blocks execution (on_fail=block)."""


class SafetyConfirmationRequiredError(RuntimeErrorBase):
    """Raised when a capability requires human confirmation before execution."""


class StepTimeoutError(RuntimeErrorBase):
    """Raised when a step exceeds its configured timeout."""