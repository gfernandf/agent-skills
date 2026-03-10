from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class FieldSpec:
    """
    Declarative description of an input/output field for a skill or capability.
    """

    type: str
    required: bool = False
    description: str | None = None
    default: Any = None


@dataclass(frozen=True)
class StepSpec:
    """
    Declarative execution step inside a skill.

    - uses: capability id or skill reference (e.g. "text.summarize", "skill:text.simple-summarize")
    - input_mapping: declarative mapping resolved by the runtime against ExecutionState
    - output_mapping: mapping from step-produced fields to runtime targets (vars.* / outputs.*)
    - config: reserved extension point for future step-level policies/options
    """

    id: str
    uses: str
    input_mapping: dict[str, Any]
    output_mapping: dict[str, str]
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillSpec:
    """
    Runtime-normalized skill definition loaded from YAML source.
    """

    id: str
    version: str
    name: str
    description: str
    inputs: dict[str, FieldSpec]
    outputs: dict[str, FieldSpec]
    steps: tuple[StepSpec, ...]
    metadata: dict[str, Any]
    channel: str | None = None
    domain: str | None = None
    slug: str | None = None
    source_file: str | None = None


@dataclass(frozen=True)
class CapabilitySpec:
    """
    Runtime-normalized capability definition loaded from YAML source.
    """

    id: str
    version: str
    description: str
    inputs: dict[str, FieldSpec]
    outputs: dict[str, FieldSpec]
    metadata: dict[str, Any]
    properties: dict[str, Any]
    requires: tuple[str, ...] = ()
    deprecated: bool | None = None
    replacement: str | None = None
    aliases: tuple[str, ...] = ()
    source_file: str | None = None


@dataclass(frozen=True)
class RuntimeEvent:
    """
    Lightweight execution event used for tracing and inspection.
    """

    type: str
    message: str
    timestamp: datetime
    step_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class StepResult:
    """
    Execution result for a single step.
    """

    step_id: str
    uses: str
    status: str
    resolved_input: dict[str, Any]
    produced_output: dict[str, Any] | None = None
    raw_result: Any = None
    # optional metadata captured during binding execution
    binding_id: str | None = None
    service_id: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass
class ExecutionState:
    """
    Mutable state for a single skill execution.
    """

    skill_id: str
    inputs: dict[str, Any]
    vars: dict[str, Any]
    outputs: dict[str, Any]
    step_results: dict[str, StepResult]
    written_targets: set[str]
    events: list[RuntimeEvent]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: str = "pending"


@dataclass(frozen=True)
class ExecutionOptions:
    """
    Runtime behavior switches for a skill execution.
    """

    fail_fast: bool = True
    max_skill_depth: int = 10
    include_raw_step_results: bool = True
    trace_enabled: bool = True


@dataclass(frozen=True)
class ExecutionRequest:
    """
    Public request object for running a skill.
    """

    skill_id: str
    inputs: dict[str, Any]
    options: ExecutionOptions = field(default_factory=ExecutionOptions)


@dataclass
class ExecutionContext:
    """
    Execution context passed through the runtime.

    Keeps execution metadata separate from the mutable execution state so the
    runtime can grow later without overloading ExecutionState.
    """

    state: ExecutionState
    options: ExecutionOptions
    depth: int = 0
    parent_skill_id: str | None = None
    lineage: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillExecutionResult:
    """
    Final result returned by the execution engine after running a skill.
    """

    skill_id: str
    status: str
    outputs: dict[str, Any]
    state: ExecutionState