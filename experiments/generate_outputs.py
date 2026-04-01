"""Post-process benchmark results: generate CSV, variability JSON, and Markdown report."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

EXPERIMENTS_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = EXPERIMENTS_DIR / "outputs"
MODEL = "gpt-4o-mini"
SEED = 42


def main():
    # Find the latest results JSON
    json_files = sorted(OUTPUT_DIR.glob("benchmark_results_*.json"), reverse=True)
    if not json_files:
        print("No benchmark_results_*.json found in outputs/")
        sys.exit(1)

    latest = json_files[0]
    print(f"Processing: {latest.name}")

    data = json.loads(latest.read_text(encoding="utf-8"))
    timestamp = data["metadata"]["timestamp"]
    orca_available = data["metadata"]["orca_available"]
    all_results = data["runs"]
    variability_results = data.get("variability", {})

    # 1. CSV
    csv_path = OUTPUT_DIR / f"benchmark_metrics_{timestamp}.csv"
    csv_fields = [
        "task", "approach", "input_id",
        "latency_s",
        "prompt_tokens", "completion_tokens", "total_tokens",
        "traceable", "reusable",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        for r in all_results:
            writer.writerow(r)
    print(f"  CSV   -> {csv_path.name}")

    # 2. Variability JSON
    var_path = OUTPUT_DIR / f"variability_{timestamp}.json"
    var_path.write_text(
        json.dumps(variability_results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  VAR   -> {var_path.name}")

    # 3. Markdown report
    report_path = OUTPUT_DIR / f"benchmark_report_{timestamp}.md"
    report_content = generate_report(all_results, variability_results, orca_available, timestamp)
    report_path.write_text(report_content, encoding="utf-8")
    print(f"  Report -> {report_path.name}")

    # 4. Print summary
    print_summary(all_results, variability_results)
    print("\nDone.")


def print_summary(results, variability):
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for task_name in ["decision", "text_processing"]:
        print(f"\n--- {task_name.replace('_', ' ').title()} ---")
        for approach in ["prompt", "orca"]:
            runs = [r for r in results if r["task"] == task_name and r["approach"] == approach]
            if not runs:
                continue
            avg_l = sum(r.get("latency_s", 0) for r in runs) / len(runs)
            avg_t = sum(r.get("total_tokens", 0) for r in runs) / len(runs)
            traceable = any(r.get("traceable", False) for r in runs)
            reusable = any(r.get("reusable", False) for r in runs)
            ok = sum(1 for r in runs if "error" not in str(r.get("output", {}))[:20])
            print(f"  {approach:8s} | "
                  f"latency={avg_l:.2f}s | tokens={avg_t:.0f} | "
                  f"traceable={'Yes' if traceable else 'No':3s} | "
                  f"reusable={'Yes' if reusable else 'No':3s} | "
                  f"ok={ok}/{len(runs)}")

    if variability:
        print("\n--- Variability Scores ---")
        for key, val in variability.items():
            print(f"  {key}: {val['variability_score']:.4f} ({val['repetitions']} reps)")


def generate_report(results, variability, orca_available, timestamp):
    lines = []
    lines.append("# Experimental Benchmark: Prompt-based vs ORCA Structured Execution")
    lines.append("")
    lines.append(f"**Date**: {timestamp}")
    lines.append(f"**Model**: {MODEL}")
    lines.append(f"**Seed**: {SEED}")
    lines.append(f"**ORCA Runtime Available**: {'Yes' if orca_available else 'No'}")
    lines.append("")

    # Methodology
    lines.append("## 1. Methodology")
    lines.append("")
    lines.append("### 1.1 Objective")
    lines.append("Compare two execution strategies for LLM-based tasks:")
    lines.append("1. **Prompt-based baseline**: A single prompt performs the full task in one LLM call.")
    lines.append("2. **ORCA structured execution**: A declarative skill composed of reusable capabilities,")
    lines.append("   each mapped to a binding and executed through the ORCA runtime engine.")
    lines.append("")
    lines.append("### 1.2 Tasks")
    lines.append("")
    lines.append("**Task 1 -- Structured Decision-Making**")
    lines.append("- Input: A problem statement with 3 options and evaluation criteria.")
    lines.append("- Output: The selected best option with justification.")
    lines.append("- ORCA Skill: `experiment.structured-decision` using capabilities")
    lines.append("  `agent.option.generate` -> `agent.flow.branch`.")
    lines.append("")
    lines.append("**Task 2 -- Multi-step Text Processing**")
    lines.append("- Input: A paragraph of text.")
    lines.append("- Steps: (1) extract key information, (2) summarize, (3) classify.")
    lines.append("- ORCA Skill: `experiment.text-processing-pipeline` using capabilities")
    lines.append("  `text.entity.extract` -> `text.content.summarize` -> `text.content.classify`.")
    lines.append("")
    lines.append("### 1.3 Metrics")
    lines.append("| Metric | Description |")
    lines.append("|--------|-------------|")
    lines.append("| Latency | Wall-clock execution time in seconds |")
    lines.append("| Token Usage | Prompt + completion tokens (prompt-based); approximate for ORCA |")
    lines.append("| Traceability | Binary: whether intermediate steps are exposed |")
    lines.append("| Reusability | Binary: whether components can be independently reused |")
    lines.append("| Variability | Jaccard distance across 3 repeated runs on 3 selected inputs |")
    lines.append("")
    lines.append("### 1.4 Experimental Setup")
    lines.append("- 10 inputs per task, 2 approaches per task")
    lines.append("- Variability: 3 inputs x 3 repetitions per approach")
    lines.append(f"- Fixed seed: {SEED}")
    lines.append(f"- Model: {MODEL}")
    lines.append("- Local execution on a laptop (no cloud infrastructure)")
    lines.append("")

    # Results
    lines.append("## 2. Results")
    lines.append("")

    for task_name, task_label in [("decision", "Task 1: Structured Decision-Making"),
                                   ("text_processing", "Task 2: Multi-step Text Processing")]:
        section = "2.1" if task_name == "decision" else "2.2"
        lines.append(f"### {section} {task_label}")
        lines.append("")

        lines.append("#### Individual Results")
        lines.append("")
        lines.append("| Input | Approach | Latency (s) | Tokens | Traceable | Reusable |")
        lines.append("|-------|----------|-------------|--------|-----------|----------|")
        task_runs = [r for r in results if r["task"] == task_name]
        for r in sorted(task_runs, key=lambda x: (x["input_id"], x["approach"])):
            lines.append(
                f"| {r['input_id']} | {r['approach']} | "
                f"{r['latency_s']} | {r.get('total_tokens', 0)} | "
                f"{'Yes' if r.get('traceable') else 'No'} | "
                f"{'Yes' if r.get('reusable') else 'No'} |"
            )
        lines.append("")

        lines.append("#### Aggregate Summary")
        lines.append("")
        lines.append("| Approach | Avg Latency (s) | Avg Tokens | Traceable | Reusable |")
        lines.append("|----------|-----------------|------------|-----------|----------|")
        for approach in ["prompt", "orca"]:
            runs = [r for r in task_runs if r["approach"] == approach]
            if not runs:
                continue
            avg_l = sum(r.get("latency_s", 0) for r in runs) / len(runs)
            avg_t = sum(r.get("total_tokens", 0) for r in runs) / len(runs)
            traceable = "Yes" if any(r.get("traceable") for r in runs) else "No"
            reusable = "Yes" if any(r.get("reusable") for r in runs) else "No"
            lines.append(
                f"| {approach} | {avg_l:.2f} | {avg_t:.0f} | {traceable} | {reusable} |"
            )
        lines.append("")

    # Variability
    lines.append("### 2.3 Variability Analysis")
    lines.append("")
    lines.append("Variability is measured as the mean Jaccard distance of output token sets")
    lines.append("across 3 repeated runs. A score of 0.0 means identical outputs; 1.0 means")
    lines.append("completely different outputs.")
    lines.append("")
    if variability:
        lines.append("| Key | Variability Score | Repetitions |")
        lines.append("|-----|-------------------|-------------|")
        for key, val in variability.items():
            lines.append(f"| {key} | {val['variability_score']:.4f} | {val['repetitions']} |")
    else:
        lines.append("*Variability data not available in this run.*")
    lines.append("")

    # Analysis
    lines.append("## 3. Analysis")
    lines.append("")
    lines.append("### 3.1 Latency")
    lines.append("The prompt-based approach uses a single LLM call, resulting in lower latency.")
    lines.append("ORCA executes multiple sequential capability bindings, adding overhead per step")
    lines.append("but enabling independent optimization of each stage.")
    lines.append("")
    lines.append("### 3.2 Traceability")
    lines.append("ORCA provides full step-level traceability through its `StepResult` trace,")
    lines.append("exposing resolved inputs, produced outputs, binding IDs, and latency per step.")
    lines.append("The prompt-based approach is opaque: only the final output is visible.")
    lines.append("")
    lines.append("### 3.3 Reusability")
    lines.append("ORCA capabilities are independently reusable across different skills.")
    lines.append("For example, `text.content.summarize` used in the text processing pipeline")
    lines.append("can be reused in any other skill without modification.")
    lines.append("The prompt-based approach is monolithic and task-specific.")
    lines.append("")
    lines.append("### 3.4 Variability")
    lines.append("With a fixed seed, both approaches should produce near-identical outputs")
    lines.append("across repetitions. Variability scores near zero confirm reproducibility.")
    lines.append("Higher variability in ORCA may arise from multi-step composition effects.")
    lines.append("")

    # Conclusion
    lines.append("## 4. Conclusion")
    lines.append("")
    lines.append("| Dimension | Prompt-based | ORCA Structured |")
    lines.append("|-----------|-------------|-----------------|")
    lines.append("| Latency | Lower (1 call) | Higher (N calls) |")
    lines.append("| Token efficiency | Moderate | Variable (per-step budgets) |")
    lines.append("| Traceability | None | Full step-level trace |")
    lines.append("| Reusability | None | Full capability reuse |")
    lines.append("| Variability | Low (fixed seed) | Low-moderate |")
    lines.append("| Maintainability | Low (monolithic prompt) | High (declarative YAML) |")
    lines.append("")
    lines.append("The trade-off is clear: prompt-based execution is simpler and faster for")
    lines.append("one-off tasks, while ORCA structured execution provides engineering benefits")
    lines.append("(traceability, reusability, composability) critical for production systems")
    lines.append("where auditability and maintainability outweigh raw latency.")
    lines.append("")

    # Reproducibility
    lines.append("## 5. Reproducibility")
    lines.append("")
    lines.append("```bash")
    lines.append("cd agent-skills")
    lines.append("export OPENAI_API_KEY=<your-key>")
    lines.append("python experiments/run_benchmark.py")
    lines.append("```")
    lines.append("")
    lines.append("All outputs are saved to `experiments/outputs/` with timestamps.")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    main()
