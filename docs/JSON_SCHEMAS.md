# JSON Schemas

agent-skills publishes JSON Schema definitions for all public-facing
data models. These can be used for:

- **Validation**: Verify skill YAML files conform to the expected structure.
- **Code generation**: Generate typed clients in any language.
- **Documentation**: Self-describing contracts for integrations.
- **IDE support**: Auto-completion and error checking in YAML editors.

## Available schemas

All schemas are in `docs/schemas/` and follow the
[JSON Schema 2020-12](https://json-schema.org/draft/2020-12/schema) draft.

| Schema | Description |
|---|---|
| `SkillSpec.schema.json` | Skill definition (id, steps, inputs, outputs) |
| `StepSpec.schema.json` | Execution step inside a skill |
| `FieldSpec.schema.json` | Input/output field descriptor |
| `CapabilitySpec.schema.json` | Capability definition |
| `ExecutionState.schema.json` | Runtime execution state |
| `StepResult.schema.json` | Step execution result |
| `RuntimeEvent.schema.json` | Execution trace event |
| `ExecutionOptions.schema.json` | Execution configuration switches |
| `FrameState.schema.json` | Reasoning context (CognitiveState) |
| `WorkingState.schema.json` | Working memory (CognitiveState) |
| `OutputState.schema.json` | Result metadata (CognitiveState) |
| `TraceState.schema.json` | Execution trace with data lineage |
| `TraceStep.schema.json` | Individual trace step |
| `TraceMetrics.schema.json` | Aggregate execution metrics |
| `WebhookSubscription.schema.json` | Webhook subscription model |
| `HttpErrorContract.schema.json` | Canonical error response (all surfaces) |

## Validating skill files

Use the built-in validator:

```bash
# Single file
python tooling/validate_skill_schema.py skills/my_skill.yaml

# Entire directory
python tooling/validate_skill_schema.py skills/

# Example skills
python tooling/validate_skill_schema.py examples/
```

Output:
```
✓ examples/simple_text_skill.yaml
✓ examples/multi_step_pipeline.yaml
✗ skills/broken_skill.yaml
  - skill.id: required field missing
  - skill.steps[0].uses: required field missing

────────────────────────────────────────
Files: 3  Errors: 2
```

## Regenerating schemas

Schemas are generated from the authoritative Python dataclasses:

```bash
python tooling/generate_json_schemas.py
```

This regenerates all 15 schemas in `docs/schemas/`.

## Using schemas in editors

### VS Code with YAML extension

Add to `.vscode/settings.json`:

```json
{
  "yaml.schemas": {
    "./docs/schemas/SkillSpec.schema.json": "skills/**/*.yaml"
  }
}
```

This enables auto-completion and validation for skill YAML files.
