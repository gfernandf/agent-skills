"""
Filesystem baseline service module.
Provides baseline implementations for filesystem-related capabilities.
"""
import os
from pathlib import Path

_FS_ROOT = os.getenv("AGENT_SKILLS_FS_ROOT", os.getcwd())


def _validate_path(path: str) -> str:
    """Canonicalize *path* and ensure it lives inside the allowed root.

    The allowed root is determined by the AGENT_SKILLS_FS_ROOT environment
    variable, falling back to the working directory at import time.

    Raises ValueError if the resolved path escapes the allowed root.
    """
    root = os.path.realpath(_FS_ROOT)
    resolved = os.path.realpath(path)
    # os.path.commonpath raises ValueError if paths are on different drives
    try:
        common = os.path.commonpath([root, resolved])
    except ValueError:
        raise ValueError(
            f"Access denied: '{path}' is outside the allowed root."
        )
    if common != root:
        raise ValueError(
            f"Access denied: '{path}' resolves outside the allowed root."
        )
    return resolved

def read_file(path, mode=None):
    """
    Read the contents of a file.
    
    Args:
        path (str): The file path.
        mode (str): "text" or "binary". Defaults to "text".
    
    Returns:
        dict: {"content": str} for text mode, {"bytes": bytes} for binary mode.
    """
    try:
        safe_path = _validate_path(path)
    except ValueError as e:
        return {"content": str(e)}
    try:
        if mode == "binary":
            with open(safe_path, 'rb') as f:
                content = f.read()
            return {"bytes": content}
        else:
            with open(safe_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return {"content": content}
    except Exception as e:
        return {"content": f"Error reading file: {str(e)}"}