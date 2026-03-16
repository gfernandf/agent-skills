#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(cmd, capture_output=True, text=True)
    if check and cp.returncode != 0:
        raise RuntimeError(
            f"Command failed ({cp.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{cp.stdout}\n"
            f"stderr:\n{cp.stderr}"
        )
    return cp


def _run_json(cmd: list[str], *, expect_code: int = 0) -> dict[str, Any]:
    cp = subprocess.run(cmd, capture_output=True, text=True)
    if cp.returncode != expect_code:
        raise RuntimeError(
            f"Unexpected return code {cp.returncode} (expected {expect_code}) for: {' '.join(cmd)}\n"
            f"stdout:\n{cp.stdout}\n"
            f"stderr:\n{cp.stderr}"
        )

    text = cp.stdout.strip()
    if not text:
        raise RuntimeError(f"No stdout JSON for command: {' '.join(cmd)}")

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON stdout for command: {' '.join(cmd)}\n{text}") from e


def _read_trace_id_from_audit(runtime_root: Path) -> str:
    audit_path = runtime_root / "artifacts" / "runtime_skill_audit.jsonl"
    if not audit_path.exists():
        raise RuntimeError(f"Audit file not found: {audit_path}")

    with audit_path.open("r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except Exception:
                continue
            if not isinstance(item, dict):
                continue
            trace_id = item.get("trace_id")
            if isinstance(trace_id, str) and trace_id:
                return trace_id

    raise RuntimeError("No trace_id entries found in runtime audit file")


def _http_json(url: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return resp.getcode(), payload
    except urllib.error.HTTPError as e:
        payload: dict[str, Any] = {}
        try:
            payload = json.loads(e.read().decode("utf-8"))
        except Exception:
            payload = {"error": {"message": str(e)}}
        return e.code, payload


def _start_http_server(runtime_root: Path, registry_root: Path, host_root: Path, port: int) -> subprocess.Popen[str]:
    cmd = [
        sys.executable,
        str(runtime_root / "tooling" / "run_customer_http_api.py"),
        "--port",
        str(port),
        "--runtime-root",
        str(runtime_root),
        "--registry-root",
        str(registry_root),
        "--host-root",
        str(host_root),
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    base = f"http://127.0.0.1:{port}"
    for _ in range(40):
        try:
            code, _ = _http_json(f"{base}/v1/health")
            if code == 200:
                return proc
        except Exception:
            pass
        time.sleep(0.25)

    proc.terminate()
    raise RuntimeError("HTTP server did not become ready in time")


def _stop_proc(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _mcp_call(runtime_root: Path, registry_root: Path, host_root: Path, requests: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    cmd = [
        sys.executable,
        str(runtime_root / "tooling" / "run_customer_mcp_bridge.py"),
        "--runtime-root",
        str(runtime_root),
        "--registry-root",
        str(registry_root),
        "--host-root",
        str(host_root),
    ]
    lines = "\n".join(json.dumps(r, ensure_ascii=False) for r in requests) + "\n"
    try:
        cp = subprocess.run(cmd, input=lines, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            "MCP bridge timed out while processing smoke requests. "
            f"partial_stdout:\n{(e.stdout or '')}\npartial_stderr:\n{(e.stderr or '')}"
        ) from e
    if cp.returncode != 0:
        raise RuntimeError(
            f"MCP bridge failed with code {cp.returncode}\nstdout:\n{cp.stdout}\nstderr:\n{cp.stderr}"
        )

    by_id: dict[str, dict[str, Any]] = {}
    for line in cp.stdout.splitlines():
        raw = line.strip()
        if not raw or not raw.startswith("{"):
            continue
        try:
            item = json.loads(raw)
        except Exception:
            continue
        if isinstance(item, dict) and "id" in item:
            by_id[str(item["id"])] = item

    return by_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Slice 3 smoke tests for gateway layer")
    parser.add_argument("--runtime-root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--registry-root", type=Path, default=None)
    parser.add_argument("--host-root", type=Path, default=None)
    parser.add_argument("--http-port", type=int, default=8093)
    args = parser.parse_args()

    runtime_root = args.runtime_root.resolve()
    registry_root = (args.registry_root or (runtime_root.parent / "agent-skill-registry")).resolve()
    host_root = (args.host_root or runtime_root).resolve()

    python = sys.executable
    cli = runtime_root / "cli" / "main.py"

    print("[smoke] building attach target index")
    _run(
        [
            python,
            str(runtime_root / "tooling" / "build_attach_target_index.py"),
            "--runtime-root",
            str(runtime_root),
        ]
    )

    print("[smoke] selecting attach target_ref from audit")
    target_ref = _read_trace_id_from_audit(runtime_root)

    print("[smoke] cli list")
    cli_list = _run_json(
        [
            python,
            str(cli),
            "list",
            "--domain",
            "web",
            "--role",
            "utility",
            "--invocation",
            "attach",
            "--json",
            "--runtime-root",
            str(runtime_root),
            "--registry-root",
            str(registry_root),
            "--host-root",
            str(host_root),
        ]
    )
    assert cli_list.get("count", 0) >= 1, "CLI list expected at least one attachable web utility"

    print("[smoke] cli gateway diagnostics")
    cli_diag = _run_json(
        [
            python,
            str(cli),
            "gateway-diagnostics",
            "--json",
            "--runtime-root",
            str(runtime_root),
            "--registry-root",
            str(registry_root),
            "--host-root",
            str(host_root),
        ]
    )
    cache_diag = cli_diag.get("gateway", {}).get("cache", {})
    process_diag = cli_diag.get("gateway", {}).get("process", {})
    assert isinstance(process_diag.get("pid"), int), "CLI diagnostics missing process pid"
    assert isinstance(process_diag.get("started_at_utc"), str), "CLI diagnostics missing process started_at_utc"
    assert isinstance(process_diag.get("uptime_seconds"), (int, float)), "CLI diagnostics missing process uptime"
    assert isinstance(process_diag.get("operation_counts"), dict), "CLI diagnostics missing operation counts"
    assert isinstance(cache_diag.get("discovery_evidence"), dict), "CLI diagnostics missing discovery cache stats"
    assert isinstance(cache_diag.get("attach_targets"), dict), "CLI diagnostics missing attach cache stats"

    print("[smoke] cli gateway reset metrics")
    cli_reset = _run_json(
        [
            python,
            str(cli),
            "gateway-reset-metrics",
            "--clear-cache",
            "--json",
            "--runtime-root",
            str(runtime_root),
            "--registry-root",
            str(registry_root),
            "--host-root",
            str(host_root),
        ]
    )
    cli_reset_info = cli_reset.get("gateway", {}).get("reset", {})
    assert cli_reset_info.get("ok") is True, "CLI reset should return ok=true"
    assert cli_reset_info.get("clear_cache") is True, "CLI reset should echo clear_cache=true"

    print("[smoke] cli diagnostics persistence")
    cli_diag_after_reset_1 = _run_json(
        [
            python,
            str(cli),
            "gateway-diagnostics",
            "--json",
            "--runtime-root",
            str(runtime_root),
            "--registry-root",
            str(registry_root),
            "--host-root",
            str(host_root),
        ]
    )
    cli_diag_after_reset_2 = _run_json(
        [
            python,
            str(cli),
            "gateway-diagnostics",
            "--json",
            "--runtime-root",
            str(runtime_root),
            "--registry-root",
            str(registry_root),
            "--host-root",
            str(host_root),
        ]
    )
    counts_1 = cli_diag_after_reset_1.get("gateway", {}).get("process", {}).get("operation_counts", {})
    counts_2 = cli_diag_after_reset_2.get("gateway", {}).get("process", {}).get("operation_counts", {})
    assert int(counts_2.get("diagnostics", 0)) >= int(counts_1.get("diagnostics", 0)) + 1, (
        "CLI diagnostics counter should persist and increment across separate invocations"
    )
    persistence = cli_diag_after_reset_2.get("gateway", {}).get("persistence", {})
    assert persistence.get("enabled") is True, "CLI diagnostics should report persistence enabled"
    assert isinstance(persistence.get("state_path"), str), "CLI diagnostics should include persistence state path"

    print("[smoke] cli discover")
    cli_discover = _run_json(
        [
            python,
            str(cli),
            "discover",
            "summarize web page",
            "--domain",
            "web",
            "--limit",
            "3",
            "--json",
            "--runtime-root",
            str(runtime_root),
            "--registry-root",
            str(registry_root),
            "--host-root",
            str(host_root),
        ]
    )
    assert len(cli_discover.get("results", [])) >= 1, "CLI discover expected at least one result"
    first_cli_result = cli_discover["results"][0]
    assert isinstance(first_cli_result.get("reason_codes"), list), "CLI discover reason_codes missing"
    assert isinstance(first_cli_result.get("score_breakdown"), dict), "CLI discover score_breakdown missing"
    assert isinstance(first_cli_result.get("evidence"), dict), "CLI discover evidence missing"

    print("[smoke] cli attach invalid")
    cli_attach_invalid = _run_json(
        [
            python,
            str(cli),
            "attach",
            "web.fetch-summary",
            "--target-type",
            "output",
            "--target-ref",
            target_ref,
            "--json",
            "--runtime-root",
            str(runtime_root),
            "--registry-root",
            str(registry_root),
            "--host-root",
            str(host_root),
        ],
        expect_code=2,
    )
    assert cli_attach_invalid.get("ok") is False, "CLI attach invalid should return ok=false"

    print("[smoke] cli attach valid")
    input_path = runtime_root / "artifacts" / "slice3_attach_input.json"
    input_path.write_text(
        json.dumps({"content": "https://example.com"}, ensure_ascii=False),
        encoding="utf-8",
    )
    cli_attach_valid = _run_json(
        [
            python,
            str(cli),
            "attach",
            "web.page-summary",
            "--target-type",
            "output",
            "--target-ref",
            target_ref,
            "--input-file",
            str(input_path),
            "--json",
            "--runtime-root",
            str(runtime_root),
            "--registry-root",
            str(registry_root),
            "--host-root",
            str(host_root),
        ]
    )
    assert cli_attach_valid.get("skill_id") == "web.page-summary", "CLI attach valid skill_id mismatch"
    assert isinstance(cli_attach_valid.get("attach_context"), dict), "CLI attach explainability context missing"

    print("[smoke] http server")
    proc = _start_http_server(runtime_root, registry_root, host_root, args.http_port)
    base = f"http://127.0.0.1:{args.http_port}"
    try:
        print("[smoke] http list")
        code, http_list = _http_json(f"{base}/v1/skills/list?domain=web&invocation=attach")
        assert code == 200 and len(http_list.get("skills", [])) >= 1, "HTTP list failed"

        print("[smoke] http discover")
        code, http_discover = _http_json(
            f"{base}/v1/skills/discover",
            method="POST",
            body={"intent": "summarize web page", "domain": "web", "limit": 3},
        )
        assert code == 200 and len(http_discover.get("results", [])) >= 1, "HTTP discover failed"
        first_http_result = http_discover["results"][0]
        assert isinstance(first_http_result.get("reason_codes"), list), "HTTP discover reason_codes missing"
        assert isinstance(first_http_result.get("score_breakdown"), dict), "HTTP discover score_breakdown missing"
        assert isinstance(first_http_result.get("evidence"), dict), "HTTP discover evidence missing"

        print("[smoke] http diagnostics")
        code, http_diag = _http_json(f"{base}/v1/skills/diagnostics")
        assert code == 200, "HTTP diagnostics failed"
        http_process = http_diag.get("gateway", {}).get("process", {})
        assert isinstance(http_process.get("pid"), int), "HTTP diagnostics missing process pid"
        assert isinstance(http_process.get("started_at_utc"), str), "HTTP diagnostics missing process started_at_utc"
        assert isinstance(http_process.get("uptime_seconds"), (int, float)), "HTTP diagnostics missing process uptime"
        assert isinstance(http_process.get("operation_counts"), dict), "HTTP diagnostics missing operation counts"
        http_cache = http_diag.get("gateway", {}).get("cache", {})
        assert isinstance(http_cache.get("discovery_evidence"), dict), "HTTP diagnostics discovery cache missing"
        assert isinstance(http_cache.get("attach_targets"), dict), "HTTP diagnostics attach cache missing"
        http_persistence = http_diag.get("gateway", {}).get("persistence", {})
        assert http_persistence.get("enabled") is True, "HTTP diagnostics should report persistence enabled"
        assert isinstance(http_persistence.get("state_path"), str), "HTTP diagnostics should include persistence state path"

        print("[smoke] http attach invalid")
        code, http_attach_invalid = _http_json(
            f"{base}/v1/skills/web.fetch-summary/attach",
            method="POST",
            body={"target_type": "output", "target_ref": target_ref, "inputs": {}},
        )
        assert code == 400, "HTTP attach invalid should return 400"
        assert http_attach_invalid.get("error", {}).get("code") == "invalid_request", "HTTP attach invalid code mismatch"
    finally:
        _stop_proc(proc)

    print("[smoke] mcp tools")
    mcp = _mcp_call(
        runtime_root,
        registry_root,
        host_root,
        requests=[
            {"id": "1", "method": "tools/list"},
            {
                "id": "2",
                "method": "tools/call",
                "params": {
                    "name": "skill.list",
                    "arguments": {"domain": "web", "invocation": "attach"},
                },
            },
            {
                "id": "3",
                "method": "tools/call",
                "params": {
                    "name": "skill.discover",
                    "arguments": {"intent": "summarize web page", "domain": "web", "limit": 2},
                },
            },
            {
                "id": "4",
                "method": "tools/call",
                "params": {
                    "name": "skill.attach",
                    "arguments": {
                        "skill_id": "web.fetch-summary",
                        "target_type": "output",
                        "target_ref": target_ref,
                        "inputs": {},
                    },
                },
            },
            {
                "id": "5",
                "method": "tools/call",
                "params": {
                    "name": "skill.diagnostics",
                    "arguments": {},
                },
            },
            {
                "id": "6",
                "method": "tools/call",
                "params": {
                    "name": "skill.metrics.reset",
                    "arguments": {"clear_cache": True},
                },
            },
            {
                "id": "7",
                "method": "tools/call",
                "params": {
                    "name": "skill.diagnostics",
                    "arguments": {},
                },
            },
        ],
    )

    tools = mcp.get("1", {}).get("result", {}).get("tools", [])
    names = {tool.get("name") for tool in tools if isinstance(tool, dict)}
    assert (
        "skill.discover" in names
        and "skill.list" in names
        and "skill.attach" in names
        and "skill.diagnostics" in names
        and "skill.metrics.reset" in names
    ), "MCP tools missing"

    mcp_list = mcp.get("2", {}).get("result", {})
    assert len(mcp_list.get("skills", [])) >= 1, "MCP skill.list failed"

    mcp_discover = mcp.get("3", {}).get("result", {})
    assert len(mcp_discover.get("results", [])) >= 1, "MCP skill.discover failed"
    first_mcp_result = mcp_discover["results"][0]
    assert isinstance(first_mcp_result.get("reason_codes"), list), "MCP discover reason_codes missing"
    assert isinstance(first_mcp_result.get("score_breakdown"), dict), "MCP discover score_breakdown missing"
    assert isinstance(first_mcp_result.get("evidence"), dict), "MCP discover evidence missing"

    mcp_attach_invalid = mcp.get("4", {}).get("error", {})
    assert mcp_attach_invalid.get("code") == "invalid_request", "MCP skill.attach invalid should be invalid_request"

    mcp_diag = mcp.get("5", {}).get("result", {})
    mcp_process = mcp_diag.get("gateway", {}).get("process", {})
    assert isinstance(mcp_process.get("pid"), int), "MCP diagnostics missing process pid"
    assert isinstance(mcp_process.get("started_at_utc"), str), "MCP diagnostics missing process started_at_utc"
    assert isinstance(mcp_process.get("uptime_seconds"), (int, float)), "MCP diagnostics missing process uptime"
    assert isinstance(mcp_process.get("operation_counts"), dict), "MCP diagnostics missing operation counts"
    mcp_cache = mcp_diag.get("gateway", {}).get("cache", {})
    assert isinstance(mcp_cache.get("discovery_evidence"), dict), "MCP diagnostics discovery cache missing"
    assert isinstance(mcp_cache.get("attach_targets"), dict), "MCP diagnostics attach cache missing"
    mcp_persistence = mcp_diag.get("gateway", {}).get("persistence", {})
    assert mcp_persistence.get("enabled") is True, "MCP diagnostics should report persistence enabled"
    assert isinstance(mcp_persistence.get("state_path"), str), "MCP diagnostics should include persistence state path"

    mcp_reset = mcp.get("6", {}).get("result", {})
    reset_info = mcp_reset.get("gateway", {}).get("reset", {})
    assert reset_info.get("ok") is True, "MCP metrics reset should return ok=true"
    assert reset_info.get("clear_cache") is True, "MCP metrics reset should echo clear_cache=true"

    mcp_diag_after_reset = mcp.get("7", {}).get("result", {})
    op_counts_after_reset = mcp_diag_after_reset.get("gateway", {}).get("process", {}).get("operation_counts", {})
    assert op_counts_after_reset.get("reset_metrics") == 1, "MCP reset counter should be 1 after reset"

    print("[smoke] slice3 PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
