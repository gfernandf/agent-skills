#!/usr/bin/env python3
"""Reproducible benchmark script for paper-ready comparison data.

Measures cold-start latency, per-skill execution time, and throughput
across all skills using deterministic Python baselines (no API keys needed).

Usage::

    python tooling/benchmark_paper.py                     # full run (markdown)
    python tooling/benchmark_paper.py --json              # machine-readable
    python tooling/benchmark_paper.py --skill text.translate-summary  # single
    python tooling/benchmark_paper.py --runs 10           # 10 iterations each

Outputs a reproducible table suitable for inclusion in academic papers.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from runtime.engine_factory import build_runtime_components
from runtime.models import ExecutionOptions, ExecutionRequest
from runtime.skill_loader import YamlSkillLoader


def _build_engine(registry_root: Path, runtime_root: Path):
    components = build_runtime_components(
        registry_root=registry_root,
        runtime_root=runtime_root,
        host_root=runtime_root,
        mcp_client_registry=None,
    )
    return components.engine


def _default_inputs_for_skill(skill) -> dict:
    """Generate minimal valid inputs for a skill."""
    inputs = {}
    for name, spec in skill.inputs.items():
        if not getattr(spec, "required", True):
            continue
        typ = getattr(spec, "type", "string")
        if typ == "string":
            inputs[name] = "Benchmark test input text for reproducible measurement."
        elif typ == "integer":
            inputs[name] = 50
        elif typ == "boolean":
            inputs[name] = True
        elif typ == "object":
            inputs[name] = {}
        elif typ == "array":
            inputs[name] = []
        else:
            inputs[name] = "test"
    return inputs


def run_benchmark(
    registry_root: Path,
    runtime_root: Path,
    skill_filter: str | None = None,
    num_runs: int = 5,
) -> dict:
    engine = _build_engine(registry_root, runtime_root)
    skill_loader = YamlSkillLoader(registry_root)

    # Discover all skills
    import yaml

    skills_root = registry_root / "skills"
    skill_ids = []
    for skill_file in sorted(skills_root.glob("**/skill.yaml")):
        try:
            raw = yaml.safe_load(skill_file.read_text(encoding="utf-8"))
            sid = raw.get("id")
            if sid and sid != "domain.skill-name":  # skip TEMPLATE
                skill_ids.append(sid)
        except Exception:
            pass

    if skill_filter:
        skill_ids = [s for s in skill_ids if s == skill_filter]

    # Cold start: time engine creation
    t0 = time.perf_counter()
    _build_engine(registry_root, runtime_root)
    cold_start_ms = (time.perf_counter() - t0) * 1000

    results = []
    for skill_id in skill_ids:
        try:
            skill = skill_loader.get_skill(skill_id)
        except Exception:
            results.append(
                {
                    "skill_id": skill_id,
                    "status": "load_error",
                    "runs": 0,
                }
            )
            continue

        inputs = _default_inputs_for_skill(skill)
        timings: list[float] = []
        status = "ok"

        for i in range(num_runs):
            request = ExecutionRequest(
                skill_id=skill_id,
                inputs=inputs,
                options=ExecutionOptions(),
                channel="benchmark",
            )
            t0 = time.perf_counter()
            try:
                engine.execute(request)
                elapsed = (time.perf_counter() - t0) * 1000
                timings.append(elapsed)
            except Exception as exc:
                elapsed = (time.perf_counter() - t0) * 1000
                if i == 0:
                    status = f"exec_error: {type(exc).__name__}"
                timings.append(elapsed)

        entry = {
            "skill_id": skill_id,
            "status": status,
            "runs": len(timings),
            "steps": len(skill.steps),
        }
        if timings:
            entry["mean_ms"] = round(statistics.mean(timings), 2)
            entry["median_ms"] = round(statistics.median(timings), 2)
            entry["stdev_ms"] = (
                round(statistics.stdev(timings), 2) if len(timings) > 1 else 0.0
            )
            entry["min_ms"] = round(min(timings), 2)
            entry["max_ms"] = round(max(timings), 2)
            entry["p95_ms"] = (
                round(sorted(timings)[int(len(timings) * 0.95)], 2)
                if len(timings) >= 5
                else entry["max_ms"]
            )

        results.append(entry)

    env = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "date": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    }

    return {
        "environment": env,
        "cold_start_ms": round(cold_start_ms, 2),
        "num_runs": num_runs,
        "total_skills": len(skill_ids),
        "results": results,
    }


def format_markdown(data: dict) -> str:
    lines = []
    env = data["environment"]
    lines.append("# Agent Skills Benchmark Results")
    lines.append("")
    lines.append(f"- **Date**: {env['date']}")
    lines.append(f"- **Python**: {env['python']}")
    lines.append(f"- **Platform**: {env['platform']}")
    lines.append(f"- **Cold start**: {data['cold_start_ms']:.1f} ms")
    lines.append(f"- **Iterations per skill**: {data['num_runs']}")
    lines.append(f"- **Skills benchmarked**: {data['total_skills']}")
    lines.append("")

    lines.append(
        "| Skill | Steps | Mean (ms) | Median (ms) | p95 (ms) | Min (ms) | Max (ms) | Status |"
    )
    lines.append(
        "|-------|------:|----------:|------------:|---------:|---------:|---------:|--------|"
    )

    for r in sorted(data["results"], key=lambda x: x.get("mean_ms", 9999)):
        if "mean_ms" in r:
            lines.append(
                f"| {r['skill_id']} | {r['steps']} "
                f"| {r['mean_ms']:.1f} | {r['median_ms']:.1f} "
                f"| {r['p95_ms']:.1f} | {r['min_ms']:.1f} "
                f"| {r['max_ms']:.1f} | {r['status']} |"
            )
        else:
            lines.append(f"| {r['skill_id']} | — | — | — | — | — | — | {r['status']} |")

    lines.append("")
    # Summary stats
    ok_results = [r for r in data["results"] if "mean_ms" in r and r["status"] == "ok"]
    if ok_results:
        means = [r["mean_ms"] for r in ok_results]
        lines.append(
            f"**Summary**: {len(ok_results)} skills executed successfully. "
            f"Mean across all: {statistics.mean(means):.1f} ms, "
            f"fastest: {min(means):.1f} ms, "
            f"slowest: {max(means):.1f} ms."
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Reproducible benchmark for paper")
    parser.add_argument("--registry-root", type=Path, default=None)
    parser.add_argument("--runtime-root", type=Path, default=None)
    parser.add_argument("--skill", default=None, help="Benchmark single skill")
    parser.add_argument("--runs", type=int, default=5, help="Iterations per skill")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", type=Path, default=None, help="Write results to file")
    args = parser.parse_args()

    runtime_root = args.runtime_root or PROJECT_ROOT
    registry_root = args.registry_root or (PROJECT_ROOT.parent / "agent-skill-registry")

    print(f"Running benchmark ({args.runs} iterations per skill)...", file=sys.stderr)
    data = run_benchmark(registry_root, runtime_root, args.skill, args.runs)

    if args.json:
        output = json.dumps(data, indent=2, ensure_ascii=False)
    else:
        output = format_markdown(data)

    if args.out:
        args.out.write_text(output, encoding="utf-8")
        print(f"Results written to {args.out}", file=sys.stderr)
    else:
        print(output)

    failed = sum(1 for r in data["results"] if r["status"] != "ok")
    return 1 if failed > data["total_skills"] // 2 else 0


if __name__ == "__main__":
    sys.exit(main())
