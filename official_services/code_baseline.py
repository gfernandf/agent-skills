"""
Code baseline service module.
Provides baseline implementations for code-related capabilities.
"""

import io
import sys
from contextlib import redirect_stdout, redirect_stderr

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
    if language.lower() != "python":
        return {"result": None, "stdout": "", "stderr": f"Unsupported language: {language}"}
    
    # Capture stdout and stderr
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    result = None
    try:
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            # Use exec for statements, eval for expressions
            try:
                result = eval(code)
            except SyntaxError:
                exec(code)
    except Exception as e:
        stderr_capture.write(str(e))
    
    return {
        "result": result,
        "stdout": stdout_capture.getvalue(),
        "stderr": stderr_capture.getvalue()
    }

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