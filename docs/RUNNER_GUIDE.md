# Runner Guide

This document explains how the runtime runner works, from skill input to final outputs.

## 1) What the Runner Is

The runner is the execution subsystem in runtime/ that:

- loads skill and capability definitions
- builds an execution plan
- resolves and executes each step
- maps capability/service responses back into skill outputs
- emits execution events and structured logs

Primary entrypoint for manual usage is cli/main.py.

## 2) End-to-End Flow

Execution path (high-level):

1. CLI builds ExecutionRequest
2. ExecutionEngine loads skill and initializes ExecutionState
3. Scheduler builds DAG from step `config.depends_on` declarations
4. Scheduler dispatches steps (parallel when dependencies allow, sequential by default):
   - InputMapper resolves step input from inputs/vars/outputs refs
   - If uses starts with skill:, NestedSkillRunner executes recursively
   - Else CapabilityExecutor delegates to BindingExecutor
5. BindingExecutor pipeline:
   - BindingResolver selects binding
   - ServiceResolver resolves service descriptor
   - RequestBuilder builds protocol payload from input.* template
   - ProtocolRouter dispatches to protocol invoker
   - ResponseMapper maps response.* into capability outputs
6. OutputMapper writes step outputs to vars.* and outputs.*
7. ExecutionEngine validates required final outputs
8. SkillExecutionResult is returned

## 3) Core Runtime Modules

State and model layer:

- runtime/models.py: typed runtime data contracts
- runtime/execution_state.py: mutable execution state + runtime events
- runtime/errors.py: typed runtime exceptions

Planning and orchestration:

- runtime/skill_loader.py: loads and normalizes skill specs
- runtime/capability_loader.py: loads and normalizes capability specs
- runtime/execution_planner.py: prepares step order
- runtime/scheduler.py: DAG-based step scheduler (parallel/sequential)
- runtime/execution_engine.py: orchestrates whole run
- runtime/nested_skill_runner.py: executes skill:<id> steps

Step input/output mapping:

- runtime/reference_resolver.py: resolves data references
- runtime/input_mapper.py: materializes step input
- runtime/output_mapper.py: writes produced values to runtime targets

Binding execution layer:

- runtime/binding_registry.py: loads services, bindings, defaults
- runtime/active_binding_map.py: active override map
- runtime/binding_resolver.py: chooses effective binding
- runtime/service_resolver.py: resolves service descriptor
- runtime/request_builder.py: builds invocation payload
- runtime/protocol_router.py: routes by protocol kind
- runtime/response_mapper.py: maps invocation response to capability output
- runtime/binding_executor.py: full binding execution pipeline
- runtime/capability_executor.py: runtime adapter around binding executor

Protocol invokers:

- runtime/pythoncall_invoker.py
- runtime/openapi_invoker.py
- runtime/openrpc_invoker.py
- runtime/mcp_invoker.py

OpenAPI invoker runtime knobs (metadata-driven):

- binding metadata:
   - `method` (default `POST`)
   - `timeout_seconds` (overrides service/default timeout)
   - `headers` (string-to-string map merged over service headers)
   - `response_mode` (`json` default, `text`, or `raw`)
- service metadata:
   - `timeout_seconds` (used when binding does not override)
   - `headers` (base header map)

Observability:

- runtime/observability.py: structured logs, trace context, redaction

## 4) Trace and Events

Two complementary tracing surfaces exist:

1. Runtime events (in ExecutionState.events)
- event type/message/timestamp/step_id/trace_id/data

2. Structured logs (JSON lines)
- skill/step/capability lifecycle
- service lifecycle for critical services
- correlation through trace_id

Trace propagation:

- trace_id can be passed in ExecutionRequest
- CLI supports --trace-id in run and trace commands
- nested skills inherit parent trace_id

## 5) How to Run

Basic execution:

- python cli/main.py run <skill_id>
- python cli/main.py run <skill_id> --input "{\"key\":\"value\"}"
- python cli/main.py run <skill_id> --input-file input.json

Execution with trace correlation:

- python cli/main.py run <skill_id> --trace-id trace-001
- python cli/main.py trace <skill_id> --trace-id trace-001

System checks:

- python cli/main.py doctor

OpenAPI checks from CLI:

- python cli/main.py openapi verify-bindings --all
- python cli/main.py openapi verify-bindings --scenario tooling/openapi_scenarios/data.schema.validate.mock.json
- python cli/main.py openapi verify-invoker
- python cli/main.py openapi verify-errors

## 6) Validation and Health Commands

Contracts:

- python tooling/test_capability_contracts.py

Smoke:

- python tooling/verify_smoke_capabilities.py --report-file artifacts/smoke_report.json

Coverage and consistency:

- python tooling/compute_runtime_coverage.py
- python tooling/compute_runtime_stats.py
- python tooling/compute_skill_executability.py

Registry side:

- python ../agent-skill-registry/tools/validate_registry.py
- python ../agent-skill-registry/tools/generate_catalog.py
- python ../agent-skill-registry/tools/registry_stats.py

## 7) Failure Model (Practical)

Common failure categories:

- Input mapping errors: missing input.* fields required by a step
- Binding resolution errors: no binding or invalid default selection
- Service resolution errors: binding points to missing/invalid service
- Request/response mapping errors: template points to missing fields
- Protocol routing/invocation errors: unsupported or failing protocol path
- Final output validation errors: required skill outputs not produced

Debug order that works well:

1. Re-run with trace command and fixed trace_id
2. Inspect structured logs filtered by trace_id
3. Inspect failing step mapping in skill yaml
4. Inspect binding request/response templates
5. Confirm service implementation output shape

## 8) Configuration Surfaces

Repository-level:

- bindings/official/
- services/official/
- policies/official_default_selection.yaml

Host-level overrides (.agent-skills):

- services.yaml
- bindings/local/
- bindings/candidate/
- active_bindings.json
- overrides.yaml

## 9) Design Constraints

Current runner behavior intentionally keeps:

- DAG-based step scheduling with backward-compatible implicit sequential deps
- explicit `depends_on: []` to opt into parallel execution
- explicit mapping instead of implicit field matching
- strict response mapping (missing fields fail fast)
- protocol abstraction via invoker routing
- thread-safe state mutations via _StateLock during parallel execution

See docs/SCHEDULER.md for full scheduler documentation.

## 10) Current Baseline

As documented in docs/PROJECT_STATUS.md, runner baseline is currently stable with:

- 45/45 contract pass
- 8/8 smoke pass
- full capability coverage and skill executability (45/45 capabilities, 36/36 skills)
- DAG scheduler functional tests: 5/5
- DAG scheduler stress tests: 5/5

This is the recommended baseline before starting MCP/OpenAPI adapter expansion.
