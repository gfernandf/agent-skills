from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from runtime.checkpoint import dict_to_state, state_to_dict
from runtime.models import ExecutionState


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@runtime_checkable
class CheckpointStoreBackend(Protocol):
    def save_checkpoint(
        self,
        run_id: str,
        checkpoint_id: str,
        payload: dict[str, Any],
    ) -> None: ...

    def load_checkpoint(
        self,
        run_id: str,
        checkpoint_id: str,
    ) -> dict[str, Any] | None: ...

    def list_checkpoints(self, run_id: str) -> list[dict[str, Any]]: ...


class FileCheckpointStoreBackend:
    """Store checkpoints as JSON files under a run-scoped directory."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def save_checkpoint(
        self,
        run_id: str,
        checkpoint_id: str,
        payload: dict[str, Any],
    ) -> None:
        run_dir = self.root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / f"{checkpoint_id}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
            encoding="utf-8",
        )

    def load_checkpoint(
        self,
        run_id: str,
        checkpoint_id: str,
    ) -> dict[str, Any] | None:
        path = self.root / run_id / f"{checkpoint_id}.json"
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
        return json.loads(raw)

    def list_checkpoints(self, run_id: str) -> list[dict[str, Any]]:
        run_dir = self.root / run_id
        if not run_dir.exists():
            return []
        records: list[dict[str, Any]] = []
        for path in sorted(run_dir.glob("*.json")):
            try:
                raw = path.read_text(encoding="utf-8")
                payload = json.loads(raw)
            except Exception:
                continue
            record = payload.get("record")
            if isinstance(record, dict):
                records.append(record)
        records.sort(key=lambda item: item.get("created_at", ""))
        return records


class InMemoryCheckpointStoreBackend:
    """Simple in-memory backend for tests and local execution."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, dict[str, Any]]] = {}

    def save_checkpoint(
        self,
        run_id: str,
        checkpoint_id: str,
        payload: dict[str, Any],
    ) -> None:
        self._data.setdefault(run_id, {})[checkpoint_id] = payload

    def load_checkpoint(
        self,
        run_id: str,
        checkpoint_id: str,
    ) -> dict[str, Any] | None:
        return self._data.get(run_id, {}).get(checkpoint_id)

    def list_checkpoints(self, run_id: str) -> list[dict[str, Any]]:
        records = []
        for payload in self._data.get(run_id, {}).values():
            record = payload.get("record")
            if isinstance(record, dict):
                records.append(record)
        records.sort(key=lambda item: item.get("created_at", ""))
        return records


@dataclass(frozen=True)
class CheckpointRecord:
    checkpoint_id: str
    run_id: str
    step_id: str | None
    kind: str
    created_at: str
    pending_writes: list[str]
    state_snapshot_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "kind": self.kind,
            "created_at": self.created_at,
            "pending_writes": list(self.pending_writes),
            "state_snapshot_ref": self.state_snapshot_ref,
        }


class CheckpointManager:
    """Create/list/load run checkpoints using existing state serializer."""

    def __init__(self, backend: CheckpointStoreBackend) -> None:
        self.backend = backend

    def save_checkpoint(
        self,
        *,
        run_id: str,
        state: ExecutionState,
        step_id: str | None,
        kind: str,
        pending_writes: list[str] | None = None,
        checkpoint_id: str | None = None,
    ) -> CheckpointRecord:
        checkpoint_id = checkpoint_id or f"chk_{uuid4().hex[:12]}"
        record = CheckpointRecord(
            checkpoint_id=checkpoint_id,
            run_id=run_id,
            step_id=step_id,
            kind=kind,
            created_at=_utc_now_iso(),
            pending_writes=list(pending_writes or []),
            state_snapshot_ref=f"checkpoint://{run_id}/{checkpoint_id}",
        )

        payload = {
            "record": record.to_dict(),
            "state": state_to_dict(state),
        }
        self.backend.save_checkpoint(run_id, checkpoint_id, payload)
        return record

    def load_state(
        self,
        *,
        run_id: str,
        checkpoint_id: str,
    ) -> ExecutionState | None:
        payload = self.backend.load_checkpoint(run_id, checkpoint_id)
        if not isinstance(payload, dict):
            return None
        state_dict = payload.get("state")
        if not isinstance(state_dict, dict):
            return None
        return dict_to_state(state_dict)

    def load_checkpoint(
        self,
        *,
        run_id: str,
        checkpoint_id: str,
    ) -> dict[str, Any] | None:
        payload = self.backend.load_checkpoint(run_id, checkpoint_id)
        if not isinstance(payload, dict):
            return None
        record = payload.get("record")
        if not isinstance(record, dict):
            return None
        return record

    def list_checkpoints(self, run_id: str) -> list[dict[str, Any]]:
        return self.backend.list_checkpoints(run_id)
