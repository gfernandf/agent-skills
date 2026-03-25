"""
A1 — Storage abstraction layer.

Provides a pluggable ``StorageBackend`` protocol that decouples the runtime
from local filesystem assumptions.  The default implementation wraps
``pathlib.Path`` operations so existing behaviour is unchanged.

Third parties can substitute cloud-backed implementations (S3, GCS, Redis)
by passing a custom backend to components that need persistence (audit,
run_store, diagnostics).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """Minimal contract for persistent storage operations."""

    def read_text(self, key: str) -> str:
        """Read content as UTF-8 text.  Raises ``FileNotFoundError`` when absent."""
        ...

    def write_text(self, key: str, content: str) -> None:
        """Write content atomically (best-effort) as UTF-8 text."""
        ...

    def append_text(self, key: str, content: str) -> None:
        """Append a line to the given key (file / object)."""
        ...

    def exists(self, key: str) -> bool:
        """Return True if the key exists in the backend."""
        ...

    def delete(self, key: str) -> bool:
        """Delete the key.  Return True if it existed."""
        ...

    def list_keys(self, prefix: str = "") -> list[str]:
        """List keys matching the given prefix."""
        ...


class LocalFileStorage:
    """Default backend: maps keys to files under a root directory."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def _resolve(self, key: str) -> Path:
        # Prevent path traversal
        cleaned = Path(key).name if "/" not in key and "\\" not in key else key.lstrip("/\\")
        target = (self._root / cleaned).resolve()
        if not str(target).startswith(str(self._root.resolve())):
            raise ValueError(f"Path traversal detected: {key}")
        return target

    def read_text(self, key: str) -> str:
        path = self._resolve(key)
        return path.read_text(encoding="utf-8")

    def write_text(self, key: str, content: str) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write via temp file
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            os.replace(tmp, str(path))
        except BaseException:
            os.close(fd) if not os.get_inheritable(fd) else None
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def append_text(self, key: str, content: str) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(content)

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def delete(self, key: str) -> bool:
        path = self._resolve(key)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_keys(self, prefix: str = "") -> list[str]:
        results: list[str] = []
        for p in self._root.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(self._root)).replace("\\", "/")
                if rel.startswith(prefix):
                    results.append(rel)
        return sorted(results)
