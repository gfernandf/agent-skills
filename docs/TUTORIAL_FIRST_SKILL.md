# Tutorial: Your First Skill (from zero to execution)

This step-by-step guide walks you through creating a custom skill,
service, binding, and running it in the agent-skills runtime.

**Time:** ~15 minutes · **Prerequisites:** Python 3.11+, the agent-skills repo cloned.

---

## Step 1 — Understand the Mental Model

A **skill** is a multi-step pipeline that wires together **capabilities**.
Each capability is fulfilled by a **binding** that routes to a **service**.

```
Skill (YAML pipeline)
  └─ Step → Capability (contract: inputs/outputs)
               └─ Binding (wires a protocol + service)
                     └─ Service (actual implementation)
```

## Step 2 — Define Your Capability

Create the file `agent-skill-registry/capabilities/text.greeting.generate.yaml`:

```yaml
id: text.greeting.generate
version: 1.0.0
description: Generate a personalized greeting message.

inputs:
  name:
    type: string
    required: true
    description: Name of the person to greet.
  style:
    type: string
    required: false
    description: "Tone of the greeting: formal | casual. Defaults to casual."

outputs:
  greeting:
    type: string
    description: The generated greeting text.

metadata:
  status: experimental
  tags: [text, greeting, tutorial]
```

## Step 3 — Implement the Service

Create `official_services/greeting_baseline.py`:

```python
"""Baseline greeting service for the tutorial."""


def generate_greeting(name: str, style: str | None = None) -> dict:
    if style == "formal":
        return {"greeting": f"Dear {name}, it is a pleasure to meet you."}
    return {"greeting": f"Hey {name}! 👋 What's up?"}
```

## Step 4 — Register the Service Descriptor

Create `services/official/greeting_baseline.yaml`:

```yaml
id: greeting_baseline
kind: pythoncall
module: official_services.greeting_baseline

metadata:
  description: "Tutorial baseline for text.greeting.generate."
  maintained_by: agent-skills
```

## Step 5 — Create the Binding

Create `bindings/official/text.greeting.generate/python_greeting.yaml`:

```yaml
id: python_greeting

capability: text.greeting.generate
service: greeting_baseline
protocol: pythoncall
operation: generate_greeting

request:
  name: input.name
  style: input.style

response:
  greeting: response.greeting

metadata:
  description: "Tutorial binding for text.greeting.generate."
  status: experimental
```

## Step 6 — Write the Skill

Create `examples/tutorial_greeting_skill.yaml`:

```yaml
id: tutorial.greeting
version: "1.0.0"
name: Tutorial Greeting
description: Generate a personalized greeting — tutorial example.

inputs:
  name:
    type: string
    required: true
  style:
    type: string
    required: false

outputs:
  greeting:
    type: string

steps:
  - id: greet
    uses: text.greeting.generate
    input_mapping:
      name: "inputs.name"
      style: "inputs.style"
    output_mapping:
      greeting: "outputs.greeting"
```

## Step 7 — Run It

```bash
# From the agent-skills root
python -m cli.main --skill examples/tutorial_greeting_skill.yaml \
    --input '{"name": "Alice", "style": "formal"}'
```

Expected output (JSON):

```json
{
  "greeting": "Dear Alice, it is a pleasure to meet you."
}
```

## Step 8 — Validate Your Binding

```bash
python validate_bindings.py
```

This confirms that your binding request references only inputs declared
in the capability and that the response maps to valid outputs.

---

## Alternative: Use the Scaffold Wizard

Instead of creating all files manually, you can generate a skill interactively:

```bash
agent-skills scaffold --wizard
```

The wizard handles capability selection, YAML generation, and test fixture creation.
After scaffolding, validate and test with:

```bash
agent-skills test tutorial.greeting
agent-skills check-wiring tutorial.greeting
agent-skills describe tutorial.greeting --mermaid
```

See [docs/SKILL_AUTHORING.md](SKILL_AUTHORING.md) for the full authoring workflow.

---

## What's Next?

| Goal | Read |
|------|------|
| Full authoring workflow (test, export, contribute) | [docs/SKILL_AUTHORING.md](SKILL_AUTHORING.md) |
| Multi-step skills with control flow | [docs/STEP_CONTROL_FLOW.md](STEP_CONTROL_FLOW.md) |
| Using OpenAPI or MCP bindings | [docs/BINDING_GUIDE.md](BINDING_GUIDE.md) |
| CognitiveState v1 (structured memory) | [docs/COGNITIVE_STATE_V1.md](COGNITIVE_STATE_V1.md) |
| Observability & tracing | [docs/OBSERVABILITY.md](OBSERVABILITY.md) |
| 10-minute onboarding | [docs/ONBOARDING_10_MIN.md](ONBOARDING_10_MIN.md) |
