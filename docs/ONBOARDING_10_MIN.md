# Runner Onboarding (10 Minutes)

This guide gets a new developer productive with the runtime runner in about 10 minutes.

## 0) What You Are Looking At (1 min)

This repository is the runtime side of the project.

- It executes skills.
- It resolves capabilities via bindings.
- It invokes services through protocol adapters.
- It maps responses into runtime outputs.

If you only read one deep document later, read docs/RUNNER_GUIDE.md.

## 1) Mental Model (1 min)

Think of the runner as a deterministic pipeline:

inputs -> step input mapping -> capability execution -> output mapping -> final outputs

At runtime, the key orchestration path is:

- cli/main.py
- runtime/execution_engine.py
- runtime/binding_executor.py

## 2) Project Landmarks (1 min)

Start here:

- docs/PROJECT_STATUS.md
- docs/RUNNER_GUIDE.md
- docs/OBSERVABILITY.md
- tooling/verify_smoke_capabilities.py
- tooling/test_capability_contracts.py

Core runtime modules:

- runtime/execution_engine.py
- runtime/input_mapper.py
- runtime/output_mapper.py
- runtime/binding_registry.py
- runtime/binding_resolver.py
- runtime/request_builder.py
- runtime/response_mapper.py
- runtime/protocol_router.py

OpenAPI protocol support:

- runtime/openapi_invoker.py
- runtime/openapi_error_contract.py
- docs/OPENAPI_CONSTRUCTION_GUIDE.md (how to add new OpenAPI bindings)
- docs/OPENAPI_POPULATION_CHECKLIST.md (gate criteria for population phase)

Consumer-facing neutral API:

- runtime/engine_factory.py
- customer_facing/neutral_api.py
- customer_facing/http_openapi_server.py
- customer_facing/mcp_tool_bridge.py
- docs/CONSUMER_FACING_NEUTRAL_API.md

## 3) First Commands to Run (2 min)

From agent-skills root:

- python tooling/verify_smoke_capabilities.py --report-file artifacts/smoke_report.json
- python tooling/test_capability_contracts.py
- python tooling/verify_customer_facing_neutral.py
- python tooling/compute_runtime_coverage.py
- python tooling/compute_skill_executability.py

Expected baseline:

- smoke: 8/8 pass
- contracts: 45/45 pass
- coverage: 45/45
- skills executable: 31/31

Note on counts:

- The shared registry catalog (agent-skill-registry) is the source of truth for total definitions.
- The baseline above reflects the runtime-supported executable subset in this repository.

## 4) Run a Skill (2 min)

Basic run:

- python cli/main.py run <skill_id>

With inline input:

- python cli/main.py run <skill_id> --input "{\"key\":\"value\"}"

With input file:

- python cli/main.py run <skill_id> --input-file input.json

With trace correlation:

- python cli/main.py run <skill_id> --trace-id onboarding-001
- python cli/main.py trace <skill_id> --trace-id onboarding-001

Use trace_id to correlate runtime and service logs.

## 5) How a Single Step Works (1 min)

For each step in a skill:

1. InputMapper resolves references (inputs.*, vars.*, outputs.*)
2. CapabilityExecutor delegates to BindingExecutor
3. BindingResolver picks binding
4. RequestBuilder creates payload from input.* template
5. ProtocolRouter dispatches to pythoncall/openapi/openrpc/mcp invoker
6. ResponseMapper maps response.* to capability outputs
7. OutputMapper writes vars.* / outputs.*

## 6) Where to Debug First (1 min)

If execution fails, use this order:

1. Rerun with --trace-id and inspect structured logs.
2. Check step input mapping in skill yaml.
3. Check binding request/response templates.
4. Check service implementation output shape.
5. Re-run contracts and smoke.

Common failure classes:

- Input mapping errors
- Missing/invalid binding resolution
- Request/response mapping mismatches
- Protocol invocation failures
- Missing required final outputs

## 7) Registry Relationship (1 min)

The registry remains the source of truth for capability/skill definitions.

Registry docs are in the companion repo under docs/.

Consistency checks used by this runtime:

- ../agent-skill-registry/tools/validate_registry.py
- ../agent-skill-registry/tools/generate_catalog.py
- ../agent-skill-registry/tools/registry_stats.py

## 8) What "Good" Looks Like

You are in a good state when:

- smoke and contracts are green
- coverage and skill executability ratios are 1.0
- logs include trace_id and useful lifecycle events
- no catalog freshness drift is detected in CI

## 9) Next Read (Optional)

After this onboarding, continue with:

- docs/RUNNER_GUIDE.md for full architecture
- docs/OBSERVABILITY.md for trace and redaction tuning
- docs/PRE_MCP_OPENAPI_READINESS.md for integration baseline
