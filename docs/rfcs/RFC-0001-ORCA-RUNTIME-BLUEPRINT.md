# RFC-0001: ORCA Runtime Blueprint

Status: Draft
Authors: Runtime Architecture Working Session
Date: 2026-05-26
Related: docs/ADR.md, docs/RUNNER_GUIDE.md, docs/ASYNC_EXECUTION.md, docs/OBSERVABILITY.md

## 1. Context

The current runtime already provides:

1. Deterministic skill execution and DAG scheduling.
2. Safety gating and trust-level checks.
3. Structured observability and audit records.
4. HTTP/MCP/SDK adapters.

The primary gap for production-grade agent deployment is durable operational semantics:

1. Checkpoint/resume/replay/fork as first-class runtime operations.
2. Side-effect-safe re-execution with explicit idempotency semantics.
3. Human-in-the-loop as persisted run state (not exception-only flow).

This RFC defines the target product architecture to evolve ORCA into an agent runtime platform with a clean-core migration: temporary legacy compatibility, explicit cutover, and explicit retirement.

## 2. Product Thesis

ORCA should operate as an execution operating system for intelligent workflows:

1. Durable execution like workflow runtimes.
2. Contract/version/policy rigor like data platforms.
3. Developer ergonomics and deployment flow like modern platform tooling.
4. Side-effect safety stronger than typical graph runtimes.

## 3. Architecture Planes

### 3.1 Execution Plane

Components:

1. AsyncExecutionEngine (canonical execution core).
2. Sync adapter over async core (temporary compatibility surface).
3. Scheduler.
4. Step lifecycle orchestrator.

Responsibilities:

1. Skill and nested-skill execution.
2. Control-flow semantics.
3. Retry, timeout, cancellation.
4. Step boundary hooks for checkpoints and side-effect recording.

### 3.2 Durability Plane

Components:

1. RunStore v2.
2. CheckpointStore.
3. EventStore.
4. ReplayEngine.

Responsibilities:

1. Persist run lifecycle.
2. Persist and load consistent state snapshots.
3. Persist ordered runtime event stream.
4. Support resume, replay, and fork workflows.

### 3.3 Side-Effect Safety Plane

Components:

1. SideEffectLedger.
2. IdempotencyKeyResolver.
3. ReplayPolicyResolver.
4. Optional CompensationHandlers.

Responsibilities:

1. Ensure replay does not duplicate external actions by default.
2. Record request/response hashes and effect state.
3. Resolve behavior for re-execution under each replay policy.

### 3.4 Policy and Trust Plane

Components:

1. PolicyManager.
2. ApprovalManager.
3. TenantPolicyResolver.

Responsibilities:

1. Enforce trust/safety constraints.
2. Persist human approval requests and decisions.
3. Resolve effective policy by environment and tenant context.

### 3.5 Control Plane

Components:

1. Registry/metadata integration.
2. Binding activation and rollout manager.
3. Promotion and environment control.

Responsibilities:

1. Version snapshots per run.
2. Binding rollout controls (including shadow mode later).
3. Stable operational governance.

### 3.6 API and Streaming Plane

Components:

1. Python runtime API.
2. HTTP Runtime API.
3. Event streaming API.

Responsibilities:

1. Expose run lifecycle operations.
2. Expose checkpoint and trace navigation.
3. Expose approval and replay operations.

### 3.7 DX and Delivery Plane

Components:

1. CLI runtime lifecycle commands.
2. Test/eval harness.
3. Replay-pack tooling.

Responsibilities:

1. Shorten deploy-debug loop.
2. Improve reproducibility for operators and contributors.
3. Keep migration friction controlled while converging to a single clean architecture.

## 4. Canonical Runtime Entities

1. Skill.
2. Capability.
3. Binding.
4. Run.
5. Checkpoint.
6. SideEffectRecord.
7. PolicySnapshot.
8. Artifact.

## 5. Clean-Core Migration Strategy

1. Define one canonical runtime core (async-first) as target architecture.
2. Keep legacy runtime surfaces only during a bounded migration window.
3. Introduce durability, side-effect safety, and HITL directly in canonical core.
4. Keep compatibility shims thin and non-authoritative.
5. Remove legacy paths after cutover gates are met.

Migration constraints:

1. No indefinite dual-engine operation.
2. No new feature development on legacy path after cutover start.
3. Canonical semantics are owned by EventStore + RunStore v2 + CheckpointStore.

## 6. Known Collisions with Current Architecture

The following collisions are expected and require explicit decision before implementation:

1. ADR-001 Scheduler decision rejects asyncio-first scheduling while this blueprint introduces AsyncExecutionEngine.
Decision: retain current scheduler logic where possible, but execution ownership moves to async core; sync becomes adapter.

2. docs/ASYNC_EXECUTION.md declares in-memory run store semantics and non-durable lifecycle.
Decision: preserve endpoint compatibility temporarily; migrate backend behavior to durable semantics and retire non-durable mode.

3. Safety flow currently expresses human confirmation primarily through exceptions.
Decision: persisted waiting_for_human is canonical; exception-only behavior remains as temporary compatibility projection.

4. Existing observability event names are log-centric and unversioned.
Decision: EventStore versioned contract is source of truth; legacy logs remain as projection during migration.

5. Existing docs frame checkpoint.py as state serialization utility, not lifecycle primitive.
Decision: checkpoint semantics are promoted to lifecycle primitive while keeping serializer format upgrade-compatible.

## 7. Non-Goals in This RFC

1. Distributed scheduler redesign.
2. Visual studio UI productization.
3. Marketplace ecosystem expansion.
4. Broad connector expansion beyond current priority set.

## 8. Success Criteria

1. Run lifecycle supports pause/resume/replay/fork without breaking existing run/trace flows.
2. Side-effect replays are safe by policy defaults.
3. Every run captures reproducibility metadata (versions and policy snapshot).
4. Canonical runtime core is singular (no indefinite dual path).
5. Legacy path is retired after agreed cutover gates.

## 9. Follow-Up RFCs

1. RFC-0002: Durable Execution State Machine.
2. RFC-0003: Side-Effect Ledger and Replay Safety.
3. RFC-0004: Runtime APIs and Event Contract.
4. RFC-0005: Pseudocode and Integration Mapping.
5. RFC-0006: Legacy Retirement Matrix and Cutover Gates.
