from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# ════════════════════════════════════════════════════════════════
# CognitiveState v1 — Typed cognitive structures
# ════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class FrameState:
    """
    Immutable reasoning context established when the run is created.

    Answers: Why does this run exist? What are its boundaries?
    Read-only during execution — set once at creation.
    """

    goal: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    success_criteria: dict[str, Any] = field(default_factory=dict)
    assumptions: tuple[str, ...] = ()
    priority: str | None = None


@dataclass
class WorkingState:
    """
    Mutable working memory for multi-step cognitive processing.
    Dies with the run — NOT persistent memory.

    Typed slots enable structured reasoning patterns:
    - artifacts: named intermediate products (free-form)
    - entities/options/criteria/evidence/risks/hypotheses/uncertainties:
      cognitive categories, each a typed list of items
    - intermediate_decisions: reasoning checkpoints
    - messages: conversation-style accumulator
    """

    artifacts: dict[str, Any] = field(default_factory=dict)
    entities: list[dict[str, Any]] = field(default_factory=list)
    options: list[dict[str, Any]] = field(default_factory=list)
    criteria: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    risks: list[dict[str, Any]] = field(default_factory=list)
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    uncertainties: list[dict[str, Any]] = field(default_factory=list)
    intermediate_decisions: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class OutputState:
    """
    Structured result metadata for the run.

    NOT the same as state.outputs (the legacy flat dict contract).
    Describes the semantic shape and context of the final result.
    """

    result: Any = None
    result_type: str | None = None
    summary: str | None = None
    status_reason: str | None = None


@dataclass(frozen=True)
class TraceStep:
    """One step's trace entry with data lineage."""

    step_id: str
    capability_id: str
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    latency_ms: int | None = None


@dataclass
class TraceMetrics:
    """Live aggregate execution metrics — updated during execution."""

    step_count: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    elapsed_ms: int = 0


@dataclass
class TraceState:
    """Execution trace for observability and data lineage."""

    steps: list[TraceStep] = field(default_factory=list)
    metrics: TraceMetrics = field(default_factory=TraceMetrics)


# ════════════════════════════════════════════════════════════════
# Skill / Capability / Step specifications
# ════════════════════════════════════════════════════════════════


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

    - uses: capability id or skill reference (e.g. "text.content.summarize", "skill:text.simple-summarize")
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
    cognitive_hints: dict[str, Any] | None = None
    safety: dict[str, Any] | None = None


@dataclass(frozen=True)
class RuntimeEvent:
    """
    Lightweight execution event used for tracing and inspection.
    """

    type: str
    message: str
    timestamp: datetime
    step_id: str | None = None
    trace_id: str | None = None
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
    attempts_count: int | None = None
    fallback_used: bool | None = None
    conformance_profile: str | None = None
    required_conformance_profile: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    # CognitiveState v1 — data lineage
    reads: tuple[str, ...] | None = None
    writes: tuple[str, ...] | None = None
    latency_ms: int | None = None


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
    trace_id: str | None = None
    # CognitiveState v1 — cognitive structures
    frame: FrameState = field(default_factory=FrameState)
    working: WorkingState = field(default_factory=WorkingState)
    output: OutputState = field(default_factory=OutputState)
    trace: TraceState = field(default_factory=TraceState)
    extensions: dict[str, dict[str, Any]] = field(default_factory=dict)
    # CognitiveState v1 — metadata
    state_version: str = "1.0.0"
    skill_version: str | None = None
    iteration: int = 0
    current_step: str | None = None
    parent_run_id: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ExecutionOptions:
    """
    Runtime behavior switches for a skill execution.
    """

    fail_fast: bool = True
    max_skill_depth: int = 10
    include_raw_step_results: bool = True
    trace_enabled: bool = True
    required_conformance_profile: str | None = None
    audit_mode: str | None = None
    # Safety: runtime trust level for the current execution context.
    trust_level: str = "standard"
    # Safety: capabilities pre-confirmed by the caller (bypasses requires_confirmation).
    confirmed_capabilities: frozenset[str] = field(default_factory=frozenset)
    # Maximum wall-clock seconds across the entire nested-skill lineage.
    # None means no aggregate timeout (individual step timeouts still apply).
    max_lineage_timeout_seconds: float | None = None
    # Scheduler: max parallel workers. None = use env var or default (8).
    max_workers: int | None = None
    # Step: default timeout in seconds. None = use engine default (60s).
    default_step_timeout_seconds: float | None = None


@dataclass(frozen=True)
class ExecutionRequest:
    """
    Public request object for running a skill.
    """

    skill_id: str
    inputs: dict[str, Any]
    options: ExecutionOptions = field(default_factory=ExecutionOptions)
    trace_id: str | None = None
    channel: str | None = None


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
    trace_id: str | None = None
    channel: str | None = None
    # Monotonic deadline (time.monotonic()) for the entire lineage.
    # Set once at top level; passed down to nested contexts.
    deadline: float | None = None


@dataclass(frozen=True)
class SkillExecutionResult:
    """
    Final result returned by the execution engine after running a skill.
    """

    skill_id: str
    status: str
    outputs: dict[str, Any]
    state: ExecutionState
