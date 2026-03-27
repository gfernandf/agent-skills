"""Skill Triggers — declarative event-driven skill execution.

Allows skills to declare triggers in their YAML that fire execution
automatically when certain events occur.

Supported trigger types:
- ``schedule``: cron-like expressions (e.g. "every 5m", "daily 09:00")
- ``webhook``: fires when a named webhook is hit
- ``event``: fires when another skill completes (event chaining)
- ``file_change``: fires when specific files change

Trigger YAML syntax in skill.yaml::

    triggers:
      - type: schedule
        expression: "every 5m"
      - type: event
        source_skill: "data.ingest-pipeline"
        on_status: completed
      - type: webhook
        name: "my_hook"
      - type: file_change
        patterns: ["data/*.csv"]

Usage from CLI::

    agent-skills triggers list                     # List all triggered skills
    agent-skills triggers fire <event_name>        # Manually fire an event
    agent-skills triggers fire --webhook my_hook   # Fire a webhook trigger
    agent-skills triggers status                   # Show trigger registration
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml


@dataclass(frozen=True)
class TriggerSpec:
    """Parsed trigger definition from a skill YAML."""
    trigger_type: str  # schedule | event | webhook | file_change
    skill_id: str
    config: dict[str, Any]

    @property
    def expression(self) -> str | None:
        return self.config.get("expression")

    @property
    def source_skill(self) -> str | None:
        return self.config.get("source_skill")

    @property
    def on_status(self) -> str:
        return self.config.get("on_status", "completed")

    @property
    def webhook_name(self) -> str | None:
        return self.config.get("name")

    @property
    def file_patterns(self) -> list[str]:
        return self.config.get("patterns", [])


@dataclass
class TriggerEvent:
    """An event that can activate triggers."""
    event_type: str  # schedule | event | webhook | file_change
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.monotonic)

    @property
    def source_skill(self) -> str | None:
        return self.payload.get("source_skill")

    @property
    def status(self) -> str | None:
        return self.payload.get("status")

    @property
    def webhook_name(self) -> str | None:
        return self.payload.get("webhook_name")

    @property
    def changed_files(self) -> list[str]:
        return self.payload.get("changed_files", [])


@dataclass
class TriggerMatch:
    """Result of matching an event to a trigger."""
    trigger: TriggerSpec
    event: TriggerEvent
    matched_at: float = field(default_factory=time.monotonic)


class TriggerRegistry:
    """Registry of all triggers loaded from skill YAMLs.

    The registry:
    1. Scans all skill YAMLs for ``triggers:`` sections
    2. Indexes triggers by type for O(1) matching
    3. Provides match(event) → list of matching skills to fire
    """

    def __init__(self) -> None:
        self._triggers: list[TriggerSpec] = []
        self._by_type: dict[str, list[TriggerSpec]] = {}
        self._by_webhook: dict[str, list[TriggerSpec]] = {}
        self._by_source_skill: dict[str, list[TriggerSpec]] = {}

    @property
    def trigger_count(self) -> int:
        return len(self._triggers)

    def load_from_skills_root(self, skills_root: Path) -> int:
        """Scan all skill.yaml files under ``skills_root`` for trigger definitions.

        Returns the number of triggers loaded.
        """
        count = 0
        if not skills_root.exists():
            return 0

        for skill_file in sorted(skills_root.glob("**/skill.yaml")):
            try:
                raw = yaml.safe_load(skill_file.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    continue
                skill_id = raw.get("id")
                triggers_raw = raw.get("triggers", [])
                if not isinstance(triggers_raw, list):
                    continue
                for traw in triggers_raw:
                    if not isinstance(traw, dict):
                        continue
                    ttype = traw.get("type", "")
                    if ttype not in ("schedule", "event", "webhook", "file_change"):
                        continue
                    spec = TriggerSpec(
                        trigger_type=ttype,
                        skill_id=skill_id,
                        config=traw,
                    )
                    self._register(spec)
                    count += 1
            except Exception:
                continue

        return count

    def register(self, trigger: TriggerSpec) -> None:
        """Manually register a trigger."""
        self._register(trigger)

    def _register(self, trigger: TriggerSpec) -> None:
        self._triggers.append(trigger)
        self._by_type.setdefault(trigger.trigger_type, []).append(trigger)

        if trigger.trigger_type == "webhook" and trigger.webhook_name:
            self._by_webhook.setdefault(trigger.webhook_name, []).append(trigger)
        if trigger.trigger_type == "event" and trigger.source_skill:
            self._by_source_skill.setdefault(trigger.source_skill, []).append(trigger)

    def match(self, event: TriggerEvent) -> list[TriggerMatch]:
        """Find all triggers that match the given event."""
        matches: list[TriggerMatch] = []

        candidates = self._by_type.get(event.event_type, [])

        for trigger in candidates:
            if self._matches(trigger, event):
                matches.append(TriggerMatch(trigger=trigger, event=event))

        return matches

    def list_all(self) -> list[TriggerSpec]:
        """Return all registered triggers."""
        return list(self._triggers)

    def list_by_type(self, trigger_type: str) -> list[TriggerSpec]:
        return list(self._by_type.get(trigger_type, []))

    def get_webhooks(self) -> dict[str, list[str]]:
        """Return webhook_name → list of skill_ids mapping."""
        result: dict[str, list[str]] = {}
        for name, triggers in self._by_webhook.items():
            result[name] = [t.skill_id for t in triggers]
        return result

    def get_event_chains(self) -> dict[str, list[str]]:
        """Return source_skill → list of triggered skill_ids mapping."""
        result: dict[str, list[str]] = {}
        for source, triggers in self._by_source_skill.items():
            result[source] = [t.skill_id for t in triggers]
        return result

    def to_summary(self) -> dict[str, Any]:
        """Return a JSON-serializable summary of all triggers."""
        return {
            "total_triggers": len(self._triggers),
            "by_type": {k: len(v) for k, v in self._by_type.items()},
            "webhooks": self.get_webhooks(),
            "event_chains": self.get_event_chains(),
            "triggers": [
                {
                    "skill_id": t.skill_id,
                    "type": t.trigger_type,
                    "config": t.config,
                }
                for t in self._triggers
            ],
        }

    @staticmethod
    def _matches(trigger: TriggerSpec, event: TriggerEvent) -> bool:
        """Check if a trigger matches a specific event."""
        if trigger.trigger_type != event.event_type:
            return False

        if trigger.trigger_type == "webhook":
            return trigger.webhook_name == event.webhook_name

        if trigger.trigger_type == "event":
            if trigger.source_skill != event.source_skill:
                return False
            if trigger.on_status and event.status:
                return trigger.on_status == event.status
            return True

        if trigger.trigger_type == "file_change":
            patterns = trigger.file_patterns
            if not patterns:
                return True  # match any file change
            return _any_file_matches(event.changed_files, patterns)

        if trigger.trigger_type == "schedule":
            # Schedule triggers match when the schedule expression evaluates true
            # In practice, a scheduler component would check this; here we always match
            return True

        return False


def _any_file_matches(files: list[str], patterns: list[str]) -> bool:
    """Check if any file matches any of the glob-style patterns."""
    import fnmatch
    for f in files:
        for pat in patterns:
            if fnmatch.fnmatch(f, pat):
                return True
    return False


class TriggerEngine:
    """Executes skills when trigger events fire.

    Integrates with the runtime engine to actually run the matched skills.
    """

    def __init__(
        self,
        registry: TriggerRegistry,
        execute_fn: Callable[[str, dict[str, Any]], Any],
    ) -> None:
        self.registry = registry
        self._execute_fn = execute_fn
        self._history: list[dict[str, Any]] = []

    def fire(self, event: TriggerEvent) -> list[dict[str, Any]]:
        """Fire an event and execute all matching triggers.

        Returns a list of execution results.
        """
        matches = self.registry.match(event)
        results: list[dict[str, Any]] = []

        for match in matches:
            skill_id = match.trigger.skill_id
            inputs = event.payload.copy()
            inputs["_trigger_type"] = event.event_type
            inputs["_trigger_timestamp"] = event.timestamp

            try:
                result = self._execute_fn(skill_id, inputs)
                entry = {
                    "skill_id": skill_id,
                    "trigger_type": event.event_type,
                    "status": "completed",
                    "result": result,
                }
            except Exception as exc:
                entry = {
                    "skill_id": skill_id,
                    "trigger_type": event.event_type,
                    "status": "failed",
                    "error": str(exc),
                }

            self._history.append(entry)
            results.append(entry)

        return results

    @property
    def history(self) -> list[dict[str, Any]]:
        return list(self._history)
