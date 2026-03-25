from __future__ import annotations

import importlib
import logging
import os
import threading
import time
from typing import Any

from runtime.binding_models import InvocationRequest, InvocationResponse
from runtime.errors import RuntimeErrorBase

logger = logging.getLogger(__name__)


class PythonCallInvocationError(RuntimeErrorBase):
    """Raised when a pythoncall invocation fails."""


# ── Module allowlist ─────────────────────────────────────────────
# Only modules matching one of these prefixes are permitted.
# Override via AGENT_SKILLS_PYTHONCALL_ALLOWED_MODULES (comma-separated).
_DEFAULT_ALLOWED_PREFIXES: tuple[str, ...] = (
    "official_services.",
    "official_mcp_servers.",
    "local_services.",
    "tooling.",
)

_DANGEROUS_MODULES: frozenset[str] = frozenset({
    "os", "subprocess", "shutil", "sys", "importlib",
    "ctypes", "socket", "http", "ftplib", "smtplib",
    "code", "codeop", "compileall", "py_compile",
    "pickle", "shelve", "marshal",
})


def _get_allowed_prefixes() -> tuple[str, ...]:
    """Return configured module prefixes at call time."""
    env = os.environ.get("AGENT_SKILLS_PYTHONCALL_ALLOWED_MODULES", "").strip()
    if env:
        return tuple(p.strip() for p in env.split(",") if p.strip())
    return _DEFAULT_ALLOWED_PREFIXES


def _is_module_allowed(module_name: str) -> bool:
    """Check if the module is in the allowlist and not in the blocklist."""
    base_module = module_name.split(".")[0]
    if base_module in _DANGEROUS_MODULES:
        return False
    allowed = _get_allowed_prefixes()
    return any(module_name.startswith(prefix) for prefix in allowed)


# ── Execution timeout ────────────────────────────────────────────
_DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("AGENT_SKILLS_PYTHONCALL_TIMEOUT", "30"))


class PythonCallInvoker:
    """
    Execute a binding invocation against a local Python module.

    Security controls:
    - Module allowlist: only modules with approved prefixes are importable
    - Dangerous module blocklist: os, subprocess, etc. always rejected
    - Execution timeout: configurable per-call limit (default 30s)
    - Audit logging: all invocations are logged

    v1 assumptions:
    - service.module is an importable Python module path
    - binding.operation_id is the callable name exported by that module
    - request.payload is expanded as keyword arguments
    - the callable return value becomes raw_response

    Example:
        service.module = "official_services.pdf_tools"
        binding.operation_id = "read_pdf"

        def read_pdf(path: str) -> dict[str, Any]:
            ...
    """

    def invoke(self, request: InvocationRequest) -> InvocationResponse:
        service = request.service
        binding = request.binding

        capability_id = request.context_metadata.get("capability_id")

        if service.module is None:
            raise PythonCallInvocationError(
                f"Service '{service.id}' does not define a Python module.",
                capability_id=capability_id,
            )

        # ── Security: module allowlist enforcement ────────────────
        if not _is_module_allowed(service.module):
            logger.warning(
                "pythoncall.module_blocked module=%s service=%s capability=%s",
                service.module, service.id, capability_id,
            )
            raise PythonCallInvocationError(
                f"Module '{service.module}' is not in the allowed modules list. "
                f"Permitted prefixes: {', '.join(_get_allowed_prefixes())}. "
                f"Configure via AGENT_SKILLS_PYTHONCALL_ALLOWED_MODULES.",
                capability_id=capability_id,
            )

        if not isinstance(request.payload, dict):
            raise PythonCallInvocationError(
                f"PythonCall payload for binding '{binding.id}' must be a mapping.",
                capability_id=capability_id,
            )

        logger.info(
            "pythoncall.invoke module=%s callable=%s service=%s capability=%s",
            service.module, binding.operation_id, service.id, capability_id,
        )

        try:
            module = importlib.import_module(service.module)
        except Exception as e:
            raise PythonCallInvocationError(
                f"Could not import Python module '{service.module}' for service '{service.id}'.",
                capability_id=capability_id,
                cause=e,
            ) from e

        try:
            fn = getattr(module, binding.operation_id)
        except AttributeError as e:
            raise PythonCallInvocationError(
                f"Module '{service.module}' does not expose callable '{binding.operation_id}'.",
                capability_id=capability_id,
                cause=e,
            ) from e

        if not callable(fn):
            raise PythonCallInvocationError(
                f"Object '{binding.operation_id}' in module '{service.module}' is not callable.",
                capability_id=capability_id,
            )

        # ── Security: timeout-protected execution ─────────────────
        timeout = _DEFAULT_TIMEOUT_SECONDS
        result_holder: dict[str, Any] = {}
        error_holder: dict[str, Exception] = {}

        def _run_fn() -> None:
            try:
                result_holder["value"] = fn(**request.payload)
            except TypeError as e:
                error_holder["value"] = PythonCallInvocationError(
                    f"Callable '{binding.operation_id}' in module '{service.module}' rejected the provided arguments.",
                    capability_id=capability_id,
                    cause=e,
                )
            except Exception as e:
                error_holder["value"] = PythonCallInvocationError(
                    f"Callable '{binding.operation_id}' in module '{service.module}' failed during execution.",
                    capability_id=capability_id,
                    cause=e,
                )

        start = time.perf_counter()
        worker = threading.Thread(target=_run_fn, daemon=True)
        worker.start()
        worker.join(timeout=timeout)

        duration_ms = round((time.perf_counter() - start) * 1000, 3)

        if worker.is_alive():
            logger.error(
                "pythoncall.timeout module=%s callable=%s timeout=%.1fs capability=%s",
                service.module, binding.operation_id, timeout, capability_id,
            )
            raise PythonCallInvocationError(
                f"Callable '{binding.operation_id}' in module '{service.module}' "
                f"exceeded the {timeout}s execution timeout.",
                capability_id=capability_id,
            )

        if "value" in error_holder:
            raise error_holder["value"]

        result = result_holder.get("value")

        logger.info(
            "pythoncall.complete module=%s callable=%s duration_ms=%.3f capability=%s",
            service.module, binding.operation_id, duration_ms, capability_id,
        )

        return InvocationResponse(
            status="success",
            raw_response=result,
            metadata={
                "service_id": service.id,
                "module": service.module,
                "callable": binding.operation_id,
                "duration_ms": duration_ms,
            },
        )