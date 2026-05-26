# Agent Skills

Runtime for composable AI agent skills — deterministic execution of capability-based workflows.

## Quick navigation

- **New here?** Start with [Installation](INSTALLATION.md) and the [10-Minute Onboarding](ONBOARDING_10_MIN.md)
- **Build a skill:** [Tutorial: First Skill](TUTORIAL_FIRST_SKILL.md) → [Skill Authoring Guide](SKILL_AUTHORING.md)
- **Integrate:** [Environment Variables](ENVIRONMENT_VARIABLES.md) · [MCP Integration](MCP_INTEGRATION_SLICES.md) · [OpenAPI Construction](OPENAPI_CONSTRUCTION_GUIDE.md)
- **Troubleshoot:** [Troubleshooting](TROUBLESHOOTING.md) · [Error Taxonomy](ERROR_TAXONOMY.md)
- **Architecture:** [Runner Guide](RUNNER_GUIDE.md) · [Scheduler](SCHEDULER.md) · [CognitiveState](COGNITIVE_STATE_V1.md)
- **Target Architecture RFCs:** [RFC-0001](rfcs/RFC-0001-ORCA-RUNTIME-BLUEPRINT.md) · [RFC-0002](rfcs/RFC-0002-DURABLE-EXECUTION-STATE-MACHINE.md) · [RFC-0003](rfcs/RFC-0003-SIDE-EFFECT-LEDGER-AND-REPLAY-SAFETY.md) · [RFC-0004](rfcs/RFC-0004-RUNTIME-APIS-AND-EVENT-CONTRACT.md) · [RFC-0005](rfcs/RFC-0005-INTEGRATION-PSEUDOCODE-AND-MIGRATION.md) · [RFC-0006](rfcs/RFC-0006-LEGACY-RETIREMENT-MATRIX.md)

## What is this?

Agent Skills is a **deterministic execution engine** for AI agent capabilities. It lets you:

1. **Define** atomic capabilities (summarize, classify, extract, translate…)
2. **Compose** them into multi-step skills (workflows)
3. **Execute** skills via CLI, embedded SDK, MCP, HTTP REST, or LLM tool integrations
4. **Observe** every step via structured traces, webhooks, and metrics

See the [README](https://github.com/your-org/agent-skills#readme) for the full overview.
