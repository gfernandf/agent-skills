import { hostedMcpTool, RunContext, Agent, AgentInputItem, Runner, withTrace } from "@openai/agents";
import { z } from "zod";

/**
 * ORCA Decision Agent - cleaned Agent SDK export
 *
 * This file is a cleaned version of the Agent Builder SDK export.
 *
 * Key fixes vs raw export:
 * - MCP server URL is read from ORCA_MCP_SERVER_URL instead of hardcoded ngrok.
 * - Router transform is wired correctly from router.finalOutput.decision_route.
 * - Reporter receives the structured ORCA result explicitly.
 * - MCP allowed tools are reduced to the tools needed for this demo.
 *
 * Required env:
 * - OPENAI_API_KEY
 * - ORCA_MCP_SERVER_URL
 */

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value || value.trim().length === 0) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

const ORCA_MCP_SERVER_URL = requiredEnv("ORCA_MCP_SERVER_URL");

// Minimal MCP surface for the decision-agent demo.
// The ORCA runtime executes the internal skill workflow server-side.
const mcp = hostedMcpTool({
  serverLabel: "ORCA",
  serverUrl: ORCA_MCP_SERVER_URL,
  allowedTools: [
    "skill.decision.make",
    "run.status",
    "run.cancel",
    "skill.inspect",
    "contract.inspect"
  ],
  requireApproval: "never"
});

const OrcaSchema = z.object({
  skill_used: z.string(),
  recommendation: z.string(),
  confidence_level: z.enum(["low", "medium", "high"]),
  human_readable: z.string(),
  outputs_summary: z.object({
    recommendation: z.string(),
    confidence_score: z.number(),
    confidence_level: z.enum(["low", "medium", "high"]),
    decision_quality_score: z.number(),
    decision_quality_level: z.string()
  }),
  meta: z.object({
    fallback_used: z.boolean(),
    fallback_steps_count: z.any(),
    step_diagnostics: z.array(
      z.object({
        step_id: z.string(),
        uses: z.string(),
        binding_id: z.string(),
        service_id: z.string(),
        primary_binding_id: z.string(),
        fallback_used: z.boolean(),
        attempts_count: z.any()
      })
    )
  })
});

const RouterSchema = z.object({
  decision_route: z.enum(["normal_llm", "orca_single_skill", "orca_planned_workflow"]),
  reason: z.string(),
  confidence: z.number()
});

interface OrcaContext {
  workflowInputAsText: string;
}

export type WorkflowInput = {
  input_as_text: string;
};

export type WorkflowOutput = {
  output_text: string;
};

const orcaInstructions = (runContext: RunContext<OrcaContext>, _agent: Agent<OrcaContext>) => {
  const { workflowInputAsText } = runContext.context;

  return `You are the ORCA cognitive execution node.

Primary user request:
${workflowInputAsText}

Role:
Execute the task through ORCA MCP tools with strict traceability, operational consistency, and no hallucinated diagnostics.

Core rules:
- Use the original user request as the task source.
- Ignore routing JSON as task content.
- Do not answer as a general assistant if an ORCA tool can resolve the task.
- Never invent results, diagnostics, run metadata, binding IDs, service IDs, attempt counts, or fallback status.
- If there is not enough terminal evidence, return a controlled incomplete result.

Task classification:
Classify the request as one of:
decision, research, analysis, synthesis, validation, planning, extraction, other.

Tool selection:
Select the most appropriate ORCA MCP tool based on:
- task objective
- available tool contract
- expected output
- observable environment capabilities

For this demo, decision tasks should normally use:
skill.decision.make

Input construction:
Build the tool input explicitly from the user request.
Preserve:
- user-provided options
- constraints
- context
- assumptions
- criteria
- requested output format

Always request diagnostics when supported:
_include_diagnostics=true or include_diagnostics=true.

Polling policy:
If run.status is available:
- Prefer async execution for long-running ORCA skills.
- If the first response includes a run_id, poll run.status every 2 seconds.
- Maximum polling attempts: 90.
- Stop only on terminal status: completed, failed, or canceled.
- Never treat an initial async "running" response as a final result.

If polling is not available:
- Use sync_only mode.
- Clamp max_wait_ms to 120000 maximum.
- If timeout or recoverable failure occurs, return a structured incomplete result.
- Do not start async if you cannot poll.

Finalization rules:
- Emit a substantive recommendation only after observing terminal status completed.
- If terminal status is unavailable:
  - recommendation: "not available"
  - confidence_score: 0
  - confidence_level: "low"
  - explain the observable technical cause
- Do not declare success without terminal evidence.

Decision-task requirements:
When completed, include:
- clear recommendation
- alternatives evaluated
- risks
- uncertainties
- confidence
- operational trace

Fallback and reliability:
- If fallback is used, report it explicitly.
- If a fallback affects only a non-critical step, keep the recommendation but reduce confidence appropriately.
- If a core scoring/evaluation step fails, mark the result as degraded or incomplete.

Output contract:
Return only JSON matching the schema defined by the workflow.
No prose outside JSON.
No serialized JSON inside strings unless the schema forces string fields.
All booleans must be explicit true/false.
If a required field is unavailable, use a valid default and document the limitation.`;
};

const orca = new Agent<OrcaContext>({
  name: "ORCA",
  instructions: orcaInstructions,
  model: "gpt-5.5",
  tools: [mcp],
  outputType: OrcaSchema,
  modelSettings: {
    reasoning: {
      effort: "medium"
    },
    store: true
  }
});

const normalLlm = new Agent({
  name: "Normal LLM",
  instructions: `Answer the user directly, clearly and concisely. Do not use ORCA.`,
  model: "gpt-5.5",
  modelSettings: {
    reasoning: {
      effort: "low",
      summary: "auto"
    },
    store: true
  }
});

const router = new Agent({
  name: "Router",
  instructions: `You are a workflow router.

Classify the user's request.

Choose exactly one route:

- normal_llm
- orca_single_skill
- orca_planned_workflow

Criteria:
- Simple question, short explanation, casual conversation, or simple writing -> normal_llm
- Structured decision, analysis, synthesis, validation, extraction, or simple auditable task -> orca_single_skill
- Complex multi-step workflow, explicit planning, multiple skills, strong auditability, or composition of capabilities -> orca_planned_workflow

Do not answer the task.
Do not explain outside JSON.
Return only JSON matching the schema.`,
  model: "gpt-5.5",
  outputType: RouterSchema,
  modelSettings: {
    reasoning: {
      effort: "low",
      summary: "auto"
    },
    store: true
  }
});

const report = new Agent({
  name: "Report",
  instructions: `You receive a structured ORCA result inside a JSON object with this shape:

{
  "result": { ... ORCA output ... }
}

Your task is to generate a clear, executive, useful final answer for the user.

Use only the information in result.
Do not invent facts.
Do not call tools.
Do not hide limitations.
Do not return JSON unless explicitly asked.

Available fields:
- result.skill_used
- result.recommendation
- result.confidence_level
- result.human_readable
- result.outputs_summary
- result.meta

Structure the answer as:

## Recommendation
Summarize result.recommendation.

## Confidence
Include result.confidence_level and result.outputs_summary.confidence_score if present.

## Rationale
Summarize the key reasons from result.human_readable.

## Alternatives evaluated
Extract the alternatives mentioned in result.human_readable.

## Risks and uncertainties
Extract the risks and uncertainties mentioned in result.human_readable.

## ORCA Trace
Include:
- skill used: result.skill_used
- fallback_used: result.meta.fallback_used
- fallback_steps_count: result.meta.fallback_steps_count
- executed steps: step_id + uses from result.meta.step_diagnostics

If fallback_used is true, warn that the recommendation should be treated with caution.
If fallback_used is false, state that execution completed without fallback.`,
  model: "gpt-5.5",
  modelSettings: {
    reasoning: {
      effort: "low",
      summary: "auto"
    },
    store: true
  }
});

function toUserMessage(text: string): AgentInputItem {
  return {
    role: "user",
    content: [{ type: "input_text", text }]
  };
}

export async function runWorkflow(workflow: WorkflowInput): Promise<WorkflowOutput> {
  return await withTrace("ORCA Decision Agent SDK Demo", async () => {
    const runner = new Runner({
      traceMetadata: {
        __trace_source__: "agent-sdk-cleaned",
        workflow_id: "orca_decision_agent_demo"
      }
    });

    const conversationHistory: AgentInputItem[] = [
      toUserMessage(workflow.input_as_text)
    ];

    // 1) Router
    const routerRun = await runner.run(router, conversationHistory);

    if (!routerRun.finalOutput) {
      throw new Error("Router result is undefined");
    }

    const routerOutput = routerRun.finalOutput;

    const transformResult = {
      decision_route: routerOutput.decision_route,
      user_prompt: workflow.input_as_text
    };

    // Keep router output in history for trace continuity.
    conversationHistory.push(...routerRun.newItems.map((item) => item.rawItem));

    // 2) Normal LLM branch
    if (transformResult.decision_route === "normal_llm") {
      const normalRun = await runner.run(normalLlm, conversationHistory);

      if (!normalRun.finalOutput) {
        throw new Error("Normal LLM result is undefined");
      }

      return {
        output_text: String(normalRun.finalOutput)
      };
    }

    // 3) ORCA branch
    const orcaRun = await runner.run(
      orca,
      conversationHistory,
      {
        context: {
          workflowInputAsText: transformResult.user_prompt
        }
      }
    );

    if (!orcaRun.finalOutput) {
      throw new Error("ORCA result is undefined");
    }

    const orcaOutput = orcaRun.finalOutput;

    // Keep ORCA output in trace history, but pass structured ORCA result explicitly to the reporter.
    conversationHistory.push(...orcaRun.newItems.map((item) => item.rawItem));

    const reportInput = {
      result: orcaOutput
    };

    const reportRun = await runner.run(
      report,
      [
        toUserMessage(JSON.stringify(reportInput, null, 2))
      ]
    );

    if (!reportRun.finalOutput) {
      throw new Error("Report result is undefined");
    }

    return {
      output_text: String(reportRun.finalOutput)
    };
  });
}
