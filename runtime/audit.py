from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from runtime.errors import InvalidExecutionOptionsError

_VALID_AUDIT_MODES = {"off", "standard", "full"}
_DEFAULT_AUDIT_FILE = "runtime_skill_audit.jsonl"
_DEFAULT_AUDIT_MODE = "standard"
_MAX_STR_LEN = int(os.getenv("AGENT_SKILLS_AUDIT_MAX_STR_LEN", "512"))
_MAX_COLLECTION_ITEMS = int(os.getenv("AGENT_SKILLS_AUDIT_MAX_ITEMS", "50"))
_REDACTION_TOKEN = "[REDACTED]"
_SENSITIVE_KEY_PARTS = {
    "password",
    "secret",
    "token",
    "apikey",
    "api_key",
    "authorization",
    "auth",
    "cookie",
    "set-cookie",
    "key",
    "private",
    "credential",
    "session",
}


def _lock_file(f) -> None:
    """Acquire an exclusive advisory lock (cross-platform)."""
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)


def _unlock_file(f) -> None:
    """Release the advisory lock."""
    if os.name == "nt":
        import msvcrt
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


class AuditRecorder:
    def __init__(self, runtime_root: Path) -> None:
        env_default = os.getenv("AGENT_SKILLS_AUDIT_DEFAULT_MODE", _DEFAULT_AUDIT_MODE).strip().lower()
        self.default_mode = env_default if env_default in _VALID_AUDIT_MODES else _DEFAULT_AUDIT_MODE
        configured_path = os.getenv("AGENT_SKILLS_AUDIT_PATH", "").strip()

        if configured_path:
            self.audit_file = Path(configured_path)
        else:
            self.audit_file = runtime_root / "artifacts" / _DEFAULT_AUDIT_FILE

    def resolve_mode(self, requested_mode: str | None) -> str:
        if requested_mode is None:
            return self.default_mode

        candidate = str(requested_mode).strip().lower()
        if candidate not in _VALID_AUDIT_MODES:
            raise InvalidExecutionOptionsError(
                (
                    "Invalid audit_mode. Supported values are: "
                    "off, standard, full."
                )
            )
        return candidate

    def record_execution(
        self,
        *,
        skill_id: str,
        state,
        options,
        channel: str | None,
        depth: int,
        parent_skill_id: str | None,
        lineage: tuple[str, ...],
        error: Exception | None,
    ) -> None:
        mode = self.resolve_mode(options.audit_mode)
        if mode == "off":
            return

        record = self._build_record(
            mode=mode,
            skill_id=skill_id,
            state=state,
            options=options,
            channel=channel,
            depth=depth,
            parent_skill_id=parent_skill_id,
            lineage=lineage,
            error=error,
        )

        self.audit_file.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n"
        with self.audit_file.open("a", encoding="utf-8", newline="\n") as f:
            _lock_file(f)
            try:
                f.write(line)
            finally:
                _unlock_file(f)

    def purge(
        self,
        *,
        trace_id: str | None = None,
        skill_id: str | None = None,
        older_than_days: int | None = None,
        purge_all: bool = False,
    ) -> dict[str, Any]:
        if not self.audit_file.exists():
            return {
                "source": str(self.audit_file),
                "deleted": 0,
                "kept": 0,
                "total": 0,
                "warning": "audit file not found",
            }

        if not purge_all and trace_id is None and skill_id is None and older_than_days is None:
            raise InvalidExecutionOptionsError(
                "Provide at least one purge filter (--trace-id, --skill-id, --older-than-days) or use --all."
            )

        cutoff: datetime | None = None
        if isinstance(older_than_days, int):
            if older_than_days < 0:
                raise InvalidExecutionOptionsError("older_than_days must be >= 0.")
            cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

        kept_lines: list[str] = []
        total = 0
        deleted = 0

        # Lock the audit file during the entire read-filter-replace cycle
        # to prevent concurrent appends from being lost.
        with self.audit_file.open("r+", encoding="utf-8") as f:
            _lock_file(f)
            try:
                for raw in f:
                    line = raw.rstrip("\n")
                    if not line:
                        continue
                    total += 1

                    item: dict[str, Any] | None = None
                    try:
                        parsed = json.loads(line)
                        if isinstance(parsed, dict):
                            item = parsed
                    except json.JSONDecodeError:
                        kept_lines.append(line)
                        continue

                    if item is None:
                        kept_lines.append(line)
                        continue

                    if self._should_purge_record(
                        item,
                        trace_id=trace_id,
                        skill_id=skill_id,
                        cutoff=cutoff,
                        purge_all=purge_all,
                    ):
                        deleted += 1
                        continue

                    kept_lines.append(line)

                # Atomic replace: write to temp file then rename over original.
                parent = self.audit_file.parent
                fd, tmp_path = tempfile.mkstemp(
                    dir=str(parent), prefix=".audit_purge_", suffix=".tmp",
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as tmp:
                        for line in kept_lines:
                            tmp.write(line + "\n")
                    os.replace(tmp_path, str(self.audit_file))
                except BaseException:
                    # Clean up temp file on failure
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                    raise
            finally:
                _unlock_file(f)

        return {
            "source": str(self.audit_file),
            "deleted": deleted,
            "kept": len(kept_lines),
            "total": total,
        }

    def _build_record(
        self,
        *,
        mode: str,
        skill_id: str,
        state,
        options,
        channel: str | None,
        depth: int,
        parent_skill_id: str | None,
        lineage: tuple[str, ...],
        error: Exception | None,
    ) -> dict[str, Any]:
        steps = []
        for result in state.step_results.values():
            step_item: dict[str, Any] = {
                "step_id": result.step_id,
                "uses": result.uses,
                "status": result.status,
                "duration_ms": self._duration_ms(result.started_at, result.finished_at),
                "binding_id": result.binding_id,
                "service_id": result.service_id,
                "attempts_count": result.attempts_count,
                "fallback_used": result.fallback_used,
                "conformance_profile": result.conformance_profile,
                "required_conformance_profile": result.required_conformance_profile,
                "resolved_input_hash": self._stable_hash(result.resolved_input),
                "produced_output_hash": self._stable_hash(result.produced_output),
                "error_message": self._truncate_str(result.error_message) if result.error_message else None,
            }

            if mode == "full":
                step_item["resolved_input"] = self._sanitize(result.resolved_input)
                step_item["produced_output"] = self._sanitize(result.produced_output)

            steps.append(step_item)

        record: dict[str, Any] = {
            "schema_version": "1.0",
            "audit_mode": mode,
            "trace_id": state.trace_id,
            "skill_id": skill_id,
            "status": state.status,
            "channel": channel,
            "depth": depth,
            "parent_skill_id": parent_skill_id,
            "lineage": list(lineage),
            "started_at": self._iso(state.started_at),
            "finished_at": self._iso(state.finished_at),
            "duration_ms": self._duration_ms(state.started_at, state.finished_at),
            "required_conformance_profile": options.required_conformance_profile,
            "input_hash": self._stable_hash(state.inputs),
            "output_hash": self._stable_hash(state.outputs),
            "steps": steps,
        }

        if mode == "full":
            record["inputs"] = self._sanitize(state.inputs)
            record["outputs"] = self._sanitize(state.outputs)

        if error is not None:
            record["error"] = {
                "type": type(error).__name__,
                "message": self._truncate_str(str(error)),
            }

        return record

    def _should_purge_record(
        self,
        item: dict[str, Any],
        *,
        trace_id: str | None,
        skill_id: str | None,
        cutoff: datetime | None,
        purge_all: bool,
    ) -> bool:
        if purge_all:
            return True

        if trace_id is not None and item.get("trace_id") != trace_id:
            return False

        if skill_id is not None and item.get("skill_id") != skill_id:
            return False

        if cutoff is not None:
            finished_raw = item.get("finished_at")
            if not isinstance(finished_raw, str):
                return False

            finished = self._parse_utc(finished_raw)
            if finished is None or finished >= cutoff:
                return False

        return True

    def _stable_hash(self, value: Any) -> str | None:
        if value is None:
            return None

        text = self._stable_json(value)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    def _stable_json(self, value: Any) -> str:
        try:
            return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=self._json_default)
        except Exception:
            return json.dumps(self._json_default(value), sort_keys=True, ensure_ascii=True, separators=(",", ":"))

    def _json_default(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return self._iso(value)
        if hasattr(value, "__dict__"):
            try:
                return asdict(value)
            except Exception:
                return repr(value)
        return repr(value)

    def _duration_ms(self, started_at: datetime | None, finished_at: datetime | None) -> float | None:
        if started_at is None or finished_at is None:
            return None
        return round((finished_at - started_at).total_seconds() * 1000.0, 3)

    def _iso(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _parse_utc(self, value: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _truncate_str(self, value: str | None) -> str | None:
        if value is None:
            return None
        if len(value) <= _MAX_STR_LEN:
            return value
        return value[:_MAX_STR_LEN] + "...[truncated]"

    def _is_sensitive_key(self, key: str) -> bool:
        key_lc = key.lower()
        return any(part in key_lc for part in _SENSITIVE_KEY_PARTS)

    def _sanitize(self, value: Any, key_path: tuple[str, ...] = ()) -> Any:
        if key_path and self._is_sensitive_key(key_path[-1]):
            return _REDACTION_TOKEN

        if value is None or isinstance(value, (int, float, bool)):
            return value

        if isinstance(value, str):
            return self._truncate_str(value)

        if isinstance(value, dict):
            items = list(value.items())
            sanitized = {
                str(k): self._sanitize(v, (*key_path, str(k)))
                for k, v in items[:_MAX_COLLECTION_ITEMS]
            }
            if len(items) > _MAX_COLLECTION_ITEMS:
                sanitized["_truncated_items"] = len(items) - _MAX_COLLECTION_ITEMS
            return sanitized

        if isinstance(value, (list, tuple, set)):
            seq = list(value)
            sanitized = [self._sanitize(v, key_path) for v in seq[:_MAX_COLLECTION_ITEMS]]
            if len(seq) > _MAX_COLLECTION_ITEMS:
                sanitized.append(f"...[truncated:{len(seq) - _MAX_COLLECTION_ITEMS}]")
            return sanitized

        return self._truncate_str(repr(value))