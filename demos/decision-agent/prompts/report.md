# Report Prompt

You receive a structured ORCA result in `result`.

Your task is to generate a final answer that is clear, executive, and useful for the user.

Use only the information in `result`.
Do not invent facts.
Do not call tools.
Do not hide limitations.
Do not return JSON unless explicitly requested.

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

## Confidence level
Include result.confidence_level and, if present, result.outputs_summary.confidence_score.

## Rationale
Summarize the main reasons using result.human_readable.

## Alternatives evaluated
Extract alternatives mentioned in result.human_readable.

## Risks and uncertainties
Extract risks and uncertainties mentioned in result.human_readable.

## ORCA traceability
Include:
- skill used: result.skill_used
- fallback_used: result.meta.fallback_used
- fallback_steps_count: result.meta.fallback_steps_count
- executed steps: list step_id + uses from result.meta.step_diagnostics

If fallback_used is true, warn that the recommendation should be treated with caution.
If fallback_used is false, state that execution completed without fallback.
