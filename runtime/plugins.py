"""
Plugin discovery via setuptools entry points.

Third-party packages can register extensions by adding entry points
in their pyproject.toml / setup.cfg under these groups:

    [project.entry-points."agent_skills.auth"]
    my_backend = "my_package.auth:MyAuthBackend"

    [project.entry-points."agent_skills.invoker"]
    my_protocol = "my_package.invoker:MyInvoker"

    [project.entry-points."agent_skills.binding_source"]
    community = "my_package.sources:CommunityBindings"

Usage:
    from runtime.plugins import discover_plugins
    auth_plugins = discover_plugins("agent_skills.auth")
"""
from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import Any

logger = logging.getLogger(__name__)


def discover_plugins(group: str) -> dict[str, Any]:
    """Load all entry points in the given group and return {name: loaded_obj}."""
    plugins: dict[str, Any] = {}
    eps = entry_points()
    # Python 3.12+ returns a SelectableGroups; 3.9-3.11 returns dict
    if isinstance(eps, dict):
        group_eps = eps.get(group, [])
    else:
        group_eps = eps.select(group=group)

    for ep in group_eps:
        try:
            obj = ep.load()
            plugins[ep.name] = obj
            logger.debug("Loaded plugin %s.%s → %s", group, ep.name, obj)
        except Exception as exc:
            logger.warning("Failed to load plugin %s.%s: %s", group, ep.name, exc)
    return plugins


PLUGIN_GROUPS = (
    "agent_skills.auth",
    "agent_skills.invoker",
    "agent_skills.binding_source",
)


def discover_all() -> dict[str, dict[str, Any]]:
    """Discover plugins for all known groups."""
    return {group: discover_plugins(group) for group in PLUGIN_GROUPS}
