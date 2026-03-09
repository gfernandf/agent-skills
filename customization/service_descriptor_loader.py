from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from runtime.binding_models import ServiceDescriptor
from runtime.errors import RuntimeErrorBase


class ServiceDescriptorLoadError(RuntimeErrorBase):
    """Raised when local service descriptors cannot be loaded."""


class ServiceDescriptorLoader:
    """
    Load user-defined services from:

        .agent-skills/services.yaml

    These services extend the official registry and enable local integrations.
    """

    def __init__(self, host_root: Path) -> None:
        self.host_root = host_root

    def load(self) -> list[ServiceDescriptor]:
        path = self.host_root / ".agent-skills" / "services.yaml"

        if not path.exists():
            return []

        try:
            with path.open("r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ServiceDescriptorLoadError(
                f"Invalid YAML in '{path}'.",
                cause=e,
            ) from e

        if not isinstance(raw, dict):
            raise ServiceDescriptorLoadError(
                f"File '{path}' must contain a mapping."
            )

        services = raw.get("services", {})

        if not isinstance(services, dict):
            raise ServiceDescriptorLoadError(
                f"'services' in '{path}' must be a mapping."
            )

        descriptors: list[ServiceDescriptor] = []

        for service_id, spec in services.items():
            descriptors.append(
                self._normalize_service(
                    service_id=service_id,
                    raw=spec,
                    source_file=str(path),
                )
            )

        return descriptors

    def _normalize_service(
        self,
        *,
        service_id: str,
        raw: Any,
        source_file: str,
    ) -> ServiceDescriptor:
        if not isinstance(service_id, str) or not service_id:
            raise ServiceDescriptorLoadError(
                f"Invalid service id in '{source_file}'."
            )

        if not isinstance(raw, dict):
            raise ServiceDescriptorLoadError(
                f"Service '{service_id}' in '{source_file}' must be a mapping."
            )

        kind = raw.get("kind")

        if not isinstance(kind, str) or not kind:
            raise ServiceDescriptorLoadError(
                f"Service '{service_id}' must define 'kind'."
            )

        spec_ref = raw.get("spec_ref")
        auth_ref = raw.get("auth_ref")
        base_url = raw.get("base_url")
        server = raw.get("server")
        module = raw.get("module")

        metadata = raw.get("metadata", {})

        if metadata is None:
            metadata = {}

        if not isinstance(metadata, dict):
            raise ServiceDescriptorLoadError(
                f"Service '{service_id}' metadata must be a mapping."
            )

        return ServiceDescriptor(
            id=service_id,
            kind=kind,
            spec_ref=spec_ref,
            auth_ref=auth_ref,
            base_url=base_url,
            server=server,
            module=module,
            metadata=dict(metadata),
            source="local",
            source_file=source_file,
        )