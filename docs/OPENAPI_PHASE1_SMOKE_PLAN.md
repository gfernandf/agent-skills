# OpenAPI v1 Phase 1 Smoke Plan

Date: 2026-03-11
Status: Ready for implementation
Scope: First OpenAPI integration wave on the critical smoke subset

## Goal

Phase 1 validates the OpenAPI integration pattern on the critical smoke subset before scaling to the full populated capability set.

This phase does not modify capability contracts.
It introduces OpenAPI-compatible bindings and implementation rules around a limited, operationally important subset.

## Selected Smoke Capabilities

The Phase 1 subset is the current smoke suite:

1. `text.summarize`
2. `code.execute`
3. `web.fetch`
4. `pdf.read`
5. `audio.transcribe`
6. `fs.read`
7. `data.schema.validate`
8. `agent.route`

## Current Baseline (Pythoncall)

| Capability | Current Binding | Current Service | Notes |
|---|---|---|---|
| `text.summarize` | `python_text_summarize` | `text_baseline` | Minimal request/response shape |
| `code.execute` | `python_code_execute` | `code_baseline` | High-risk service, already hardened and instrumented |
| `web.fetch` | `python_web_fetch` | `web_baseline` | High-risk service, network controls already exist |
| `pdf.read` | `python_pdf_read` | `doc_baseline` | Requires file/path validation discipline |
| `audio.transcribe` | `python_audio_transcribe` | `audio_baseline` | Input field name differs at binding layer (`audio` -> `audio_data`) |
| `fs.read` | `python_fs_read` | `fs_baseline` | Dual output shape (`content` or `bytes`) |
| `data.schema.validate` | `python_data_schema_validate` | `data_baseline` | Good candidate for deterministic OpenAPI validation pattern |
| `agent.route` | `python_agent_route` | `agent_baseline` | Current request mapping is suspicious and should be reviewed before replication |

## Phase 1 Deliverables

1. OpenAPI binding standard confirmed on the smoke subset.
2. One provider-facing OpenAPI service/binding path proven end-to-end through runtime.
3. Error mapping table applied consistently for smoke capability execution through OpenAPI.
4. Trace propagation verified with `trace_id` through request, runtime, and service logs.
5. CI test plan defined for smoke HTTP/OpenAPI contract coverage.

## Current Progress

1. `data.schema.validate` has a first provider-facing OpenAPI prototype implemented.
2. Generic OpenAPI verification harness created for reusable local-instance testing.
3. Harness commands:
   - `python tooling/verify_openapi_bindings.py --scenario tooling/openapi_scenarios/data.schema.validate.mock.json`
   - `python tooling/verify_openapi_bindings.py --all`
4. Compatibility command still supported: `python tooling/verify_openapi_data_schema_validate.py`
5. The official default binding remains `python_data_schema_validate`; OpenAPI activation is local and explicit.
6. Real local-service pilot path added for `data.schema.validate` (separate from CI mock scenario).

## Implementation Rules

1. Keep existing pythoncall bindings as the stable fallback during Phase 1.
2. Introduce OpenAPI bindings alongside existing official bindings rather than replacing them immediately.
3. Switch active/default selection only after a capability passes targeted verification.
4. Reuse existing runtime path:
   - binding resolution
   - request mapping
   - protocol routing
   - response mapping
   - output validation
5. Do not add capability-specific business logic to the adapter layer.

## Per-Capability OpenAPI Notes

### `text.summarize`
- Lowest-friction candidate.
- Good first capability to validate simple JSON body in and JSON body out.

### `code.execute`
- Must preserve timeout and output-size safety rules.
- Error normalization matters because upstream failures can be noisy.

### `web.fetch`
- Must preserve SSRF/scheme restrictions at the service boundary.
- Good candidate to verify HTTP metadata capture in tracing.

### `pdf.read`
- Must preserve path/file validation rules.
- Likely needs careful response normalization for extracted metadata.

### `audio.transcribe`
- Input field translation must remain in binding mapping, not in capability schema.
- Good example of contract-preserving field adaptation.

### `fs.read`
- Output may vary by mode; OpenAPI response schema needs a stable representation.
- Requires explicit treatment of optional `bytes` output.

### `data.schema.validate`
- Strong candidate for deterministic contract tests.
- Useful as a template for object-in/object-out bindings.

### `agent.route`
- Current baseline binding maps both `query` and `agents` from `input.input`.
- Before introducing OpenAPI, confirm whether this is intentional or a baseline simplification that should not be copied blindly.

## Recommended Implementation Order

1. `data.schema.validate`
2. `text.summarize`
3. `web.fetch`
4. `audio.transcribe`
5. `fs.read`
6. `pdf.read`
7. `code.execute`
8. `agent.route`

This order starts with low-friction mappings, then moves into I/O and high-risk services, and leaves the currently ambiguous binding last.

## Validation Inputs

Reuse the existing smoke/batch inputs as the first OpenAPI verification payloads:

1. `text.summarize`: long-form text input
2. `code.execute`: python snippet + language
3. `web.fetch`: `https://www.google.com`
4. `pdf.read`: `/tmp/test.pdf`
5. `audio.transcribe`: fake audio payload placeholder
6. `fs.read`: hosts file path in text mode
7. `data.schema.validate`: simple object + schema
8. `agent.route`: routing input question

These are baseline verification inputs only; Phase 1 implementation may add OpenAPI-specific fixtures later.

## Exit Criteria

Phase 1 is complete when:

1. The selected smoke subset is explicitly frozen as the first OpenAPI wave.
2. The implementation order is approved.
3. The fallback policy is approved: pythoncall remains available until OpenAPI verification passes.
4. The `agent.route` mapping risk is explicitly accepted or corrected before OpenAPI replication.
5. Phase 2 can start capability-by-capability using this subset as the reference pattern.

## Immediate Next Step

Use `data.schema.validate` as the reference implementation and move next to `text.summarize`, while keeping the current pythoncall defaults intact.

Construction work should follow package boundaries and commit strategy defined in `docs/OPENAPI_CONSTRUCTION_PACKAGES.md`.
For pilot real-service validation run `python tooling/verify_openapi_data_schema_validate_local_real.py`.
