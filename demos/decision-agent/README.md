# ORCA Decision Agent Demo

> Experimental OpenAI Agent Builder + MCP demo for reusable cognitive execution with ORCA.

This folder contains a working decision-agent demo that routes user intent, executes ORCA cognitive skills through MCP, and returns a structured, auditable result.

This is a reference implementation, not a production system.

## What this demo shows

- Task routing between direct LLM handling and ORCA execution paths.
- Decision execution through `skill.decision.make`.
- Structured recommendation with alternatives, risks, uncertainties, and confidence.
- Observable operational trace including executed steps and fallback status.

## Why this exists

Many agent implementations mix cognition, orchestration, and execution inside prompts.
This demo illustrates a different pattern:

- Reusable cognitive capabilities and skills in ORCA.
- Thin orchestration at the agent layer.
- Explicit runtime traceability through MCP execution.

See repository background in `ORCA.md` at the repo root.

## Architecture (simplified)

```text
User Prompt
	-> Router Agent
		-> ORCA MCP Runtime (skill.decision.make)
			-> Structured ORCA Result
				-> Report Agent
					-> Final Recommendation
```

## Demo contents

```text
demos/decision-agent/
	README.md
	sample_input.md
	sample_output.md
	prompts/
		orca.md
		report.md
		router.md
	screenshots/
		workflow.png
	sdk/
		decision-agent.cleaned.ts
		.env.example
```

### File guide

| File | Purpose |
|------|---------|
| `sample_input.md` | Canonical prompt for the legal SaaS decision scenario |
| `sample_output.md` | Real ORCA output reference with traceability details |
| `prompts/orca.md` | ORCA execution-node prompt for strict MCP traceability |
| `prompts/report.md` | Report prompt used to format the final executive response |
| `prompts/router.md` | Router prompt used to classify the workflow route |
| `screenshots/workflow.png` | Agent Builder workflow capture |
| `sdk/decision-agent.cleaned.ts` | Cleaned Agent SDK export |
| `sdk/.env.example` | Required environment variables |

## OpenAI Builder walkthrough

1. Create a decision-oriented agent flow in Agent Builder.
2. Use `prompts/router.md` for the Router node instructions.
3. Use `prompts/orca.md` for the ORCA node instructions.
4. Use `prompts/report.md` for the Report node instructions.
5. Connect the ORCA MCP server.
6. Use the input from `sample_input.md`.
7. Run and compare output with `sample_output.md`.
8. Save workflow evidence in `screenshots/workflow.png`.

## SDK + MCP setup

The cleaned SDK export is included in `sdk/decision-agent.cleaned.ts`.

### Required environment variables

- `OPENAI_API_KEY`
- `ORCA_MCP_SERVER_URL`

Example:

```env
OPENAI_API_KEY=
ORCA_MCP_SERVER_URL=http://localhost:8000/mcp
```

### MCP tools used in this demo

- `skill.decision.make`
- `run.status`
- `run.cancel`
- `skill.inspect`
- `contract.inspect`

### Running with the SDK export

This folder does not include its own `package.json` runner. Use the exported workflow in your existing Node/TypeScript environment.

Minimal invocation shape:

```ts
const result = await runWorkflow({
	input_as_text: "..."
});

console.log(result.output_text);
```

## Expected output shape

The final report should include:

- Recommendation
- Alternatives evaluated
- Risks and uncertainties
- Confidence level and score
- ORCA execution trace and fallback status

## Limitations

- Experimental demo, no production hardening.
- Depends on accessible ORCA MCP runtime.
- Decision quality depends on provided context and skill configuration.
- External market research is not automatically injected by default.

## License

MIT (see repo root `LICENSE`).
