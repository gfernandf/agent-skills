"""
Filesystem baseline service module.
Provides baseline implementations for filesystem-related capabilities.
"""

import os

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
        raise ValueError(f"Access denied: '{path}' is outside the allowed root.")
    if common != root:
        raise ValueError(f"Access denied: '{path}' resolves outside the allowed root.")
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
            with open(safe_path, "rb") as f:
                content = f.read()
            return {"bytes": content}
        else:
            with open(safe_path, "r", encoding="utf-8") as f:
                content = f.read()
            return {"content": content}
    except Exception as e:
        return {"content": f"Error reading file: {str(e)}"}


def write_file(path, content, mode=None):
    """
    Write content to a file inside the sandbox root.

    Args:
        path (str): Destination file path.
        content (str): Text to write.
        mode (str): "overwrite" (default) or "append".

    Returns:
        dict: {"path": str, "bytes_written": int}
    """
    try:
        safe_path = _validate_path(path)
    except ValueError:
        # Path escapes sandbox — create parent inside root so _validate_path
        # succeeds for new files that don't exist yet.
        root = os.path.realpath(_FS_ROOT)
        candidate = os.path.realpath(os.path.join(root, path))
        try:
            common = os.path.commonpath([root, candidate])
        except ValueError:
            return {"path": path, "bytes_written": 0}
        if common != root:
            return {"path": path, "bytes_written": 0}
        safe_path = candidate

    os.makedirs(os.path.dirname(safe_path) or ".", exist_ok=True)

    open_mode = "a" if mode == "append" else "w"
    with open(safe_path, open_mode, encoding="utf-8") as f:
        f.write(content)

    return {"path": safe_path, "bytes_written": len(content.encode("utf-8"))}


def list_files(path, pattern=None, recursive=None):
    """
    List files and directories under a given path inside the sandbox root.

    Args:
        path (str): Directory path to list.
        pattern (str): Optional glob pattern to filter (e.g. "*.py").
        recursive (bool): Whether to recurse. Defaults to False.

    Returns:
        dict: {"entries": list, "total": int}
    """
    try:
        safe_path = _validate_path(path)
    except ValueError:
        return {"entries": [], "total": 0}

    from pathlib import Path as _P

    base = _P(safe_path)
    if not base.is_dir():
        return {"entries": [], "total": 0}

    glob_pattern = pattern or "*"
    if recursive:
        matches = list(base.rglob(glob_pattern))
    else:
        matches = list(base.glob(glob_pattern))

    entries = []
    for m in sorted(matches):
        entry = {
            "name": m.name,
            "type": "directory" if m.is_dir() else "file",
            "path": str(m.relative_to(base)),
        }
        if m.is_file():
            try:
                entry["size"] = m.stat().st_size
            except OSError:
                entry["size"] = 0
        entries.append(entry)

    return {"entries": entries, "total": len(entries)}
