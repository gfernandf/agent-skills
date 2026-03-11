"""
Code baseline service module.
Provides baseline implementations for code-related capabilities.
"""

import io
import sys
import signal
import time
from contextlib import redirect_stdout, redirect_stderr

from runtime.observability import elapsed_ms, log_event

# Execution limits
_MAX_CODE_BYTES = 16_384          # 16 KB max code input
_MAX_OUTPUT_BYTES = 65_536        # 64 KB max combined output
_EXEC_TIMEOUT_SECONDS = 5

# Restricted builtins for sandboxed exec
_SAFE_BUILTINS = {
    k: __builtins__[k] if isinstance(__builtins__, dict) else getattr(__builtins__, k)
    for k in (
        "print", "len", "range", "enumerate", "zip", "map", "filter",
        "sorted", "reversed", "list", "dict", "set", "tuple", "int",
        "float", "str", "bool", "abs", "min", "max", "sum", "round",
        "type", "isinstance", "repr", "format", "chr", "ord",
        "True", "False", "None",
    )
    if (isinstance(__builtins__, dict) and k in __builtins__)
       or (not isinstance(__builtins__, dict) and hasattr(__builtins__, k))
}


def _error(msg):
    return {"result": None, "stdout": "", "stderr": msg}


def extract_diff(code_before, code_after):
    """
    Extract the diff between two code snippets.
    
    Args:
        code_before (str): The original code.
        code_after (str): The modified code.
    
    Returns:
        dict: {"diff": str}
    """
    # Baseline implementation: simple diff
    return {"diff": f"Diff: {code_before} -> {code_after}"}

def execute_code(code, language):
    """
    Execute code in the specified language.

    Args:
        code (str): The code to execute.
        language (str): The programming language.

    Returns:
        dict: {"result": object, "stdout": str, "stderr": str}
    """
    start_time = time.perf_counter()
    code_bytes = len(code.encode("utf-8", errors="ignore")) if isinstance(code, str) else None

    def _finish(payload, status, error_type=None):
        log_event(
            "service.code.execute",
            status=status,
            language=language,
            code_bytes=code_bytes,
            stderr_present=bool(payload.get("stderr")),
            duration_ms=elapsed_ms(start_time),
            error_type=error_type,
        )
        return payload

    log_event(
        "service.code.execute.start",
        language=language,
        code_bytes=code_bytes,
    )

    if not isinstance(code, str) or not code.strip():
        return _finish(_error("Invalid input: 'code' must be a non-empty string."), "rejected", "ValidationError")
    if not isinstance(language, str) or not language.strip():
        return _finish(_error("Invalid input: 'language' must be a non-empty string."), "rejected", "ValidationError")
    if len(code.encode()) > _MAX_CODE_BYTES:
        return _finish(_error(f"Code exceeds maximum allowed size ({_MAX_CODE_BYTES} bytes)."), "rejected", "PayloadTooLarge")
    if language.lower() != "python":
        return _finish(_error(f"Unsupported language: {language}. Only 'python' is supported."), "rejected", "UnsupportedLanguage")

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    result = None

    def _timeout_handler(signum, frame):
        raise TimeoutError(f"Execution exceeded {_EXEC_TIMEOUT_SECONDS}s limit.")

    # Use SIGALRM on Unix; fall back gracefully on Windows.
    has_sigalrm = hasattr(signal, "SIGALRM")
    if has_sigalrm:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(_EXEC_TIMEOUT_SECONDS)

    try:
        sandbox = {"__builtins__": _SAFE_BUILTINS}
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            try:
                result = eval(code, sandbox)
            except SyntaxError:
                exec(code, sandbox)
    except TimeoutError as e:
        stderr_capture.write(str(e))
    except Exception as e:
        stderr_capture.write(f"{type(e).__name__}: {e}")
    finally:
        if has_sigalrm:
            signal.alarm(0)

    # Truncate oversized output
    stdout_val = stdout_capture.getvalue()
    stderr_val = stderr_capture.getvalue()
    if len(stdout_val) + len(stderr_val) > _MAX_OUTPUT_BYTES:
        stdout_val = stdout_val[:_MAX_OUTPUT_BYTES]
        stderr_val = (stderr_val + " [output truncated]")[:512]

    return _finish({"result": result, "stdout": stdout_val, "stderr": stderr_val}, "completed")

def format_code(code, language):
    """
    Format code according to language conventions.
    
    Args:
        code (str): The code to format.
        language (str): The programming language.
    
    Returns:
        dict: {"formatted_code": str}
    """
    # Baseline implementation: return as-is
    return {"formatted_code": code}