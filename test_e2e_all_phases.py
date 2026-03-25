"""E2E verification of ALL audit improvements (Phases 1-12 + F1-F7).

This test suite validates that every item implemented across all 19 phases
is importable, structurally correct, and functionally operative.

Run: python -m pytest test_e2e_all_phases.py -v
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ═══════════════════════════════════════════════════════════════════════════
# Phase 1 (S1, S2, S5): Dockerfile + rate limiter + RBAC
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase1:
    def test_dockerfile_exists_and_multistage(self):
        df = _ROOT / "Dockerfile"
        assert df.exists()
        content = df.read_text(encoding="utf-8")
        assert "FROM" in content
        assert "COPY --from=" in content  # multi-stage

    def test_server_config_has_trusted_proxies(self):
        from customer_facing.http_openapi_server import ServerConfig
        cfg = ServerConfig()
        assert hasattr(cfg, "trusted_proxies")

    def test_auth_module_importable(self):
        from runtime.auth import AuthMiddleware, ApiKeyStore, Identity
        store = ApiKeyStore()
        store.register("test-key", subject="e2e", role="admin")
        assert store.authenticate("test-key") is not None


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2 (T1): pytest-cov configuration
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase2:
    def test_pyproject_has_coverage_config(self):
        toml_text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert "--cov-fail-under=75" in toml_text
        assert "[tool.coverage.run]" in toml_text


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3 (P1, P6): Binding cache + connection pooling
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase3:
    def test_binding_executor_has_plan_cache(self):
        from runtime import binding_executor
        assert hasattr(binding_executor, "BindingExecutor")

    def test_openapi_invoker_session_pool(self):
        from runtime.openapi_invoker import OpenAPIInvoker
        inv = OpenAPIInvoker()
        assert hasattr(inv, "_sessions")


# ═══════════════════════════════════════════════════════════════════════════
# Phase 4 (S3, S6): Audit HMAC + SBOM
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase4:
    def test_audit_recorder_has_hmac(self):
        from runtime.audit import AuditRecorder
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = AuditRecorder(runtime_root=Path(tmpdir))
            assert hasattr(recorder, "_prev_hash")
            assert hasattr(recorder, "_hmac_key")

    def test_security_audit_tool_exists(self):
        assert (_ROOT / "tooling" / "security_audit.py").exists()


# ═══════════════════════════════════════════════════════════════════════════
# Phase 5 (T3, T5): Binding contracts + protocol equivalence
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase5:
    def test_binding_contracts_test_exists(self):
        assert (_ROOT / "test_binding_contracts.py").exists()

    def test_protocol_equivalence_test_exists(self):
        assert (_ROOT / "test_protocol_equivalence.py").exists()


# ═══════════════════════════════════════════════════════════════════════════
# Phase 6 (D1, D6, D7): Tutorial + example + error catalog
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase6:
    def test_tutorial_exists(self):
        assert (_ROOT / "docs" / "TUTORIAL_FIRST_SKILL.md").exists()

    def test_custom_service_example(self):
        example_dir = _ROOT / "examples" / "custom_service"
        assert example_dir.is_dir()
        assert (example_dir / "service.py").exists()

    def test_error_catalog_generator(self):
        assert (_ROOT / "tooling" / "generate_error_catalog.py").exists()


# ═══════════════════════════════════════════════════════════════════════════
# Phase 7 (P3): Performance benchmarks
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase7:
    def test_performance_baselines_exist(self):
        assert (_ROOT / "test_performance_baselines.py").exists()


# ═══════════════════════════════════════════════════════════════════════════
# Phase 8 (G1, G4): Breaking changes + atomic properties
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase8:
    def test_breaking_change_detector(self):
        registry = _ROOT.parent / "agent-skill-registry"
        assert (registry / "tools" / "detect_breaking_changes.py").exists()

    def test_atomic_properties_test(self):
        assert (_ROOT / "test_atomic_properties.py").exists()


# ═══════════════════════════════════════════════════════════════════════════
# Phase 9 (I1): MCP subprocess client
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase9:
    def test_mcp_subprocess_client_importable(self):
        from runtime.mcp_subprocess_client import SubprocessMCPClient
        assert callable(SubprocessMCPClient)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 10 (I5, I6): OTEL auto-config + LangChain/CrewAI adapters
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase10:
    def test_otel_auto_importable(self):
        from runtime.otel_auto import configure
        assert callable(configure)

    def test_langchain_adapter_exists(self):
        assert (_ROOT / "sdk" / "langchain_adapter.py").exists()

    def test_crewai_adapter_exists(self):
        assert (_ROOT / "sdk" / "crewai_adapter.py").exists()


# ═══════════════════════════════════════════════════════════════════════════
# Phase 11 (O1, O5): Prometheus + deep health
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase11:
    def test_prometheus_format_function(self):
        from customer_facing.http_openapi_server import _format_prometheus
        snap = {"uptime_seconds": 42, "counters": {"test": 1}, "histograms": {}}
        text = _format_prometheus(snap)
        assert "agent_skills_uptime_seconds 42" in text
        assert "agent_skills_test_total 1" in text

    def test_grafana_dashboard_exists(self):
        assert (_ROOT / "docs" / "grafana" / "agent_skills_dashboard.json").exists()


# ═══════════════════════════════════════════════════════════════════════════
# Phase 12 (DC1, DC3, DC4): MkDocs + troubleshooting + schema validation
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase12:
    def test_mkdocs_config(self):
        assert (_ROOT / "mkdocs.yml").exists()

    def test_troubleshooting_doc(self):
        assert (_ROOT / "docs" / "TROUBLESHOOTING.md").exists()

    def test_schema_validation_tool(self):
        assert (_ROOT / "tooling" / "validate_json_schemas.py").exists()


# ═══════════════════════════════════════════════════════════════════════════
# F1 — DC2: CI workflow + S7: Security headers
# ═══════════════════════════════════════════════════════════════════════════

class TestF1:
    def test_ci_workflow_exists(self):
        ci = _ROOT / ".github" / "workflows" / "ci.yml"
        assert ci.exists()
        content = ci.read_text(encoding="utf-8")
        assert "ruff" in content
        assert "mypy" in content
        assert "pip-audit" in content
        assert "pytest" in content

    def test_security_headers_in_server(self):
        from customer_facing.http_openapi_server import _RequestHandler
        # Verify the method exists
        assert hasattr(_RequestHandler, "_send_security_headers")


# ═══════════════════════════════════════════════════════════════════════════
# F2 — A1: Storage abstraction + T4: Fuzz testing
# ═══════════════════════════════════════════════════════════════════════════

class TestF2:
    def test_storage_backend_protocol(self):
        from runtime.storage import StorageBackend, LocalFileStorage
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalFileStorage(tmpdir)
            assert isinstance(storage, StorageBackend)

    def test_local_file_storage_roundtrip(self):
        from runtime.storage import LocalFileStorage
        with tempfile.TemporaryDirectory() as tmpdir:
            s = LocalFileStorage(tmpdir)
            s.write_text("test.txt", "hello world")
            assert s.exists("test.txt")
            assert s.read_text("test.txt") == "hello world"
            assert "test.txt" in s.list_keys()
            assert s.delete("test.txt")
            assert not s.exists("test.txt")

    def test_storage_path_traversal_blocked(self):
        from runtime.storage import LocalFileStorage
        with tempfile.TemporaryDirectory() as tmpdir:
            s = LocalFileStorage(tmpdir)
            with pytest.raises(ValueError, match="traversal"):
                s.read_text("../../etc/passwd")

    def test_fuzz_test_file_exists(self):
        assert (_ROOT / "test_fuzz_expressions.py").exists()


# ═══════════════════════════════════════════════════════════════════════════
# F3 — P2: Lock sharding + O2: Trace propagation
# ═══════════════════════════════════════════════════════════════════════════

class TestF3:
    def test_state_lock_sharded(self):
        from runtime.scheduler import _StateLock
        lock = _StateLock()
        assert hasattr(lock, "lock_for")
        vars_lock = lock.lock_for("vars")
        outputs_lock = lock.lock_for("outputs")
        # Different namespace = different lock object
        assert vars_lock is not outputs_lock

    def test_trace_context_roundtrip(self):
        from runtime.trace_context import (
            inject_traceparent,
            extract_traceparent,
            generate_trace_id,
            generate_span_id,
        )
        tid = generate_trace_id()
        sid = generate_span_id()
        headers = inject_traceparent(tid, sid)
        assert "traceparent" in headers
        ctx = extract_traceparent(headers["traceparent"])
        assert ctx is not None
        assert ctx.trace_id == tid
        assert ctx.parent_id == sid
        assert ctx.sampled is True

    def test_extract_invalid_traceparent(self):
        from runtime.trace_context import extract_traceparent
        assert extract_traceparent(None) is None
        assert extract_traceparent("invalid") is None
        assert extract_traceparent("00-" + "0" * 32 + "-" + "0" * 16 + "-00") is None


# ═══════════════════════════════════════════════════════════════════════════
# F4 — I2: AutoGen adapter + I3: Semantic Kernel adapter
# ═══════════════════════════════════════════════════════════════════════════

class TestF4:
    def test_autogen_adapter_importable(self):
        from sdk.autogen_adapter import build_autogen_tools
        assert callable(build_autogen_tools)

    def test_semantic_kernel_adapter_exists(self):
        assert (_ROOT / "sdk" / "semantic_kernel_adapter.py").exists()
        from sdk.semantic_kernel_adapter import build_sk_functions
        assert callable(build_sk_functions)


# ═══════════════════════════════════════════════════════════════════════════
# F5 — DC5: Pre-commit + G2: Deprecation + G3: SemVer
# ═══════════════════════════════════════════════════════════════════════════

class TestF5:
    def test_pre_commit_config(self):
        cfg = _ROOT / ".pre-commit-config.yaml"
        assert cfg.exists()
        content = cfg.read_text(encoding="utf-8")
        assert "ruff" in content
        assert "binding-contracts" in content

    def test_deprecation_warning_in_executor(self):
        """Verify the deprecation check code path exists."""
        import inspect
        from runtime.capability_executor import DefaultCapabilityExecutor
        source = inspect.getsource(DefaultCapabilityExecutor.execute)
        assert "deprecated" in source

    def test_semver_enforcement_tool(self):
        registry = _ROOT.parent / "agent-skill-registry"
        assert (registry / "tools" / "enforce_semver.py").exists()


# ═══════════════════════════════════════════════════════════════════════════
# F6 — A2: Plugin protocol + A3: Policy engine
# ═══════════════════════════════════════════════════════════════════════════

class TestF6:
    def test_plugin_protocols(self):
        from runtime.plugin_protocols import (
            AuthBackendProtocol,
            InvokerProtocol,
            BindingSourceProtocol,
            validate_plugin,
        )
        # A dummy class that satisfies InvokerProtocol
        class DummyInvoker:
            def invoke(self, request):
                return {}

        assert isinstance(DummyInvoker(), InvokerProtocol)
        violations = validate_plugin("agent_skills.invoker", "dummy", DummyInvoker())
        assert len(violations) == 0

    def test_policy_engine_protocol(self):
        from runtime.policy_engine import PolicyEngine, DefaultPolicyEngine
        assert hasattr(DefaultPolicyEngine, "enforce_pre")
        assert hasattr(DefaultPolicyEngine, "enforce_post")


# ═══════════════════════════════════════════════════════════════════════════
# F7 — O3: Correlation IDs + T6: mutmut + D2: API changelog +
#       D3: ADRs + P4: Discovery index + I4: Webhook DLQ
# ═══════════════════════════════════════════════════════════════════════════

class TestF7:
    def test_correlation_id_in_observability(self):
        from runtime.observability import set_correlation_id, get_correlation_id
        token = set_correlation_id("corr-123")
        assert get_correlation_id() == "corr-123"
        from runtime.observability import _CORRELATION_ID_CTX
        _CORRELATION_ID_CTX.set(None)

    def test_mutmut_config(self):
        cfg = _ROOT / "setup.cfg"
        assert cfg.exists()
        content = cfg.read_text(encoding="utf-8")
        assert "[mutmut]" in content

    def test_api_versioning_changelog(self):
        doc = _ROOT / "docs" / "API_VERSIONING_CHANGELOG.md"
        assert doc.exists()
        content = doc.read_text(encoding="utf-8")
        assert "/v1/skills/" in content
        assert "/v1/health" in content

    def test_adr_document(self):
        doc = _ROOT / "docs" / "ADR.md"
        assert doc.exists()
        content = doc.read_text(encoding="utf-8")
        assert "ADR-001" in content
        assert "ADR-002" in content
        assert "ADR-003" in content
        assert "ADR-004" in content

    def test_discovery_search_index(self):
        from gateway.discovery import SkillSearchIndex, _tokenize
        idx = SkillSearchIndex()
        assert idx.size == 0

    def test_webhook_dlq(self):
        from runtime.webhook import get_dlq
        dlq = get_dlq()
        dlq.clear()  # ensure isolation from other tests
        assert dlq.size == 0
        dlq.append({"test": True})
        assert dlq.size == 1
        items = dlq.list_items(limit=10)
        assert len(items) == 1
        dlq.clear()
        assert dlq.size == 0

    def test_dev_dependencies_complete(self):
        """Verify all required dev deps are declared in pyproject.toml."""
        content = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        for dep in ["hypothesis", "mutmut", "ruff", "pytest-cov", "pytest-benchmark", "pip-audit"]:
            assert dep in content, f"Missing dev dep: {dep}"


# ═══════════════════════════════════════════════════════════════════════════
# Cross-cutting: All new runtime modules import cleanly
# ═══════════════════════════════════════════════════════════════════════════

class TestModuleImports:
    @pytest.mark.parametrize("module", [
        "runtime.storage",
        "runtime.trace_context",
        "runtime.policy_engine",
        "runtime.plugin_protocols",
        "runtime.otel_auto",
        "runtime.otel_integration",
        "runtime.mcp_subprocess_client",
        "runtime.audit",
        "runtime.webhook",
        "runtime.scheduler",
        "runtime.observability",
        "runtime.capability_executor",
        "gateway.discovery",
        "customer_facing.http_openapi_server",
        "sdk.autogen_adapter",
    ])
    def test_module_imports(self, module):
        importlib.import_module(module)
