"""Community registry federation — multi-org registry aggregation.

Allows an agent-skills instance to discover and merge capabilities and
skills from multiple remote registries (e.g. a corporate registry plus
the public community registry) into a single unified view.

Usage::

    from runtime.registry_federation import FederatedRegistry

    fed = FederatedRegistry()
    fed.add_source("community", "https://registry.agent-skills.dev/catalog")
    fed.add_source("corp", "file:///opt/corp-registry/catalog")
    combined = fed.resolve()
    # combined.capabilities  -> merged list
    # combined.skills        -> merged list, namespaced by source
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class RegistrySource:
    """A single registry source (local directory or remote URL)."""

    name: str
    url: str  # file:// or https://
    priority: int = 0  # higher wins on conflict
    trust_level: str = "community"  # official | community | experimental


@dataclass
class FederatedView:
    """Merged view returned by FederatedRegistry.resolve()."""

    capabilities: list[dict[str, Any]] = field(default_factory=list)
    skills: list[dict[str, Any]] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)


class FederatedRegistry:
    """Aggregate capabilities and skills from multiple registry sources."""

    def __init__(self) -> None:
        self._sources: list[RegistrySource] = []

    def add_source(
        self,
        name: str,
        url: str,
        *,
        priority: int = 0,
        trust_level: str = "community",
    ) -> None:
        self._sources.append(
            RegistrySource(
                name=name, url=url, priority=priority, trust_level=trust_level
            )
        )

    def _load_json(self, url: str, filename: str) -> list[dict[str, Any]]:
        """Load a JSON catalog file from a local or remote source."""
        parsed = urlparse(url)
        if parsed.scheme in ("", "file"):
            path = Path(parsed.path) / filename
            if not path.exists():
                logger.warning("Federation: %s not found at %s", filename, path)
                return []
            return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
        if parsed.scheme in ("http", "https"):
            # Lazy import — urllib is stdlib, no extra dependency
            from urllib.request import Request, urlopen

            target = f"{url.rstrip('/')}/{filename}"
            req = Request(target, headers={"Accept": "application/json"})
            with urlopen(req, timeout=15) as resp:  # noqa: S310 — user-configured URL
                return json.loads(resp.read().decode())  # type: ignore[no-any-return]
        logger.warning("Federation: unsupported scheme %s", parsed.scheme)
        return []

    def resolve(self) -> FederatedView:
        """Merge all sources into a single FederatedView.

        Conflict resolution: when the same capability ID appears in multiple
        sources, the source with the higher priority wins.  Conflicts are
        recorded for audit.
        """
        cap_map: dict[str, tuple[int, str, dict[str, Any]]] = {}
        all_skills: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []

        sorted_sources = sorted(self._sources, key=lambda s: s.priority)

        for src in sorted_sources:
            caps = self._load_json(src.url, "capabilities.json")
            for cap in caps:
                cap_id = cap.get("id", cap.get("name", ""))
                existing = cap_map.get(cap_id)
                if existing is not None and existing[0] >= src.priority:
                    conflicts.append(
                        {
                            "capability_id": cap_id,
                            "winner_source": existing[1],
                            "loser_source": src.name,
                        }
                    )
                    continue
                if existing is not None:
                    conflicts.append(
                        {
                            "capability_id": cap_id,
                            "winner_source": src.name,
                            "loser_source": existing[1],
                        }
                    )
                cap["_federation_source"] = src.name
                cap["_trust_level"] = src.trust_level
                cap_map[cap_id] = (src.priority, src.name, cap)

            skills = self._load_json(src.url, "skills.json")
            for skill in skills:
                skill["_federation_source"] = src.name
                skill["_trust_level"] = src.trust_level
                all_skills.append(skill)

        return FederatedView(
            capabilities=[v[2] for v in cap_map.values()],
            skills=all_skills,
            sources=[s.name for s in sorted_sources],
            conflicts=conflicts,
        )
