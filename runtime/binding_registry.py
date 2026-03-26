from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from runtime.binding_models import BindingSpec, ServiceDescriptor
from runtime.errors import RuntimeErrorBase


class BindingRegistryError(RuntimeErrorBase):
    """Raised when bindings/services/default policies cannot be loaded consistently."""


class BindingRegistry:
    """
    Consolidated inventory of bindings, services, and official default selections.

    Sources:
    - official services: services/official/*.yaml
    - local services: .agent-skills/services.yaml
    - official bindings: bindings/official/<capability-id>/*.yaml
    - local bindings: .agent-skills/bindings/local/<capability-id>/*.yaml
    - candidate bindings: .agent-skills/bindings/candidate/<capability-id>/*.yaml
    - official defaults: policies/official_default_selection.yaml
    """

    def __init__(self, repo_root: Path, host_root: Path | None = None) -> None:
        self.repo_root = repo_root
        self.host_root = host_root

        self._bindings_by_id: dict[str, BindingSpec] = {}
        self._bindings_by_capability: dict[str, list[BindingSpec]] = {}
        self._services_by_id: dict[str, ServiceDescriptor] = {}
        self._official_defaults: dict[str, str] = {}

        self._allowed_conformance_profiles = {"strict", "standard", "experimental"}

        self._load_all()

    def get_binding(self, binding_id: str) -> BindingSpec:
        binding = self._bindings_by_id.get(binding_id)
        if binding is None:
            raise BindingRegistryError(f"Binding '{binding_id}' not found.")
        return binding

    def get_bindings_for_capability(self, capability_id: str) -> list[BindingSpec]:
        return list(self._bindings_by_capability.get(capability_id, []))

    def get_service(self, service_id: str) -> ServiceDescriptor:
        service = self._services_by_id.get(service_id)
        if service is None:
            raise BindingRegistryError(f"Service '{service_id}' not found.")
        return service

    def get_official_default_binding_id(self, capability_id: str) -> str | None:
        return self._official_defaults.get(capability_id)

    def list_bindings(self) -> list[BindingSpec]:
        return sorted(self._bindings_by_id.values(), key=lambda b: b.id)

    def list_services(self) -> list[ServiceDescriptor]:
        return sorted(self._services_by_id.values(), key=lambda s: s.id)

    def _load_all(self) -> None:
        self._load_services()
        self._load_bindings()
        self._load_official_defaults()
        self._validate_references()

    def _load_services(self) -> None:
        official_services_root = self.repo_root / "services" / "official"
        if official_services_root.exists():
            for path in sorted(official_services_root.glob("*.yaml")):
                service = self._load_service_file(path, source="official")
                self._register_service(service)

        if self.host_root is not None:
            local_services_path = self.host_root / ".agent-skills" / "services.yaml"
            if local_services_path.exists():
                raw = self._read_yaml(local_services_path)
                if not isinstance(raw, dict):
                    raise BindingRegistryError(
                        f"Local services file '{self._safe_relpath(local_services_path)}' must be a mapping."
                    )

                services = raw.get("services", {})
                if not isinstance(services, dict):
                    raise BindingRegistryError(
                        f"Local services file '{self._safe_relpath(local_services_path)}' must define a 'services' mapping."
                    )

                for service_id, spec in services.items():
                    service = self._normalize_service_entry(
                        service_id=service_id,
                        raw=spec,
                        source="local",
                        source_file=self._safe_relpath(local_services_path),
                    )
                    self._register_service(service)

    def _load_bindings(self) -> None:
        official_bindings_root = self.repo_root / "bindings" / "official"
        if official_bindings_root.exists():
            for path in sorted(official_bindings_root.glob("*/*.yaml")):
                binding = self._load_binding_file(path, source="official")
                self._register_binding(binding)

        if self.host_root is not None:
            local_root = self.host_root / ".agent-skills" / "bindings" / "local"
            if local_root.exists():
                for path in sorted(local_root.glob("*/*.yaml")):
                    binding = self._load_binding_file(path, source="local")
                    self._register_binding(binding)

            candidate_root = self.host_root / ".agent-skills" / "bindings" / "candidate"
            if candidate_root.exists():
                for path in sorted(candidate_root.glob("*/*.yaml")):
                    binding = self._load_binding_file(path, source="candidate")
                    self._register_binding(binding)

    def _load_official_defaults(self) -> None:
        path = self.repo_root / "policies" / "official_default_selection.yaml"
        if not path.exists():
            self._official_defaults = {}
            return

        raw = self._read_yaml(path)
        if not isinstance(raw, dict):
            raise BindingRegistryError(
                f"Official defaults file '{self._safe_relpath(path)}' must be a mapping."
            )

        defaults = raw.get("defaults", {})
        if not isinstance(defaults, dict):
            raise BindingRegistryError(
                f"Official defaults file '{self._safe_relpath(path)}' must define a 'defaults' mapping."
            )

        normalized: dict[str, str] = {}
        for capability_id, binding_id in defaults.items():
            if not isinstance(capability_id, str) or not capability_id:
                raise BindingRegistryError(
                    f"Official defaults file '{self._safe_relpath(path)}' contains an invalid capability id."
                )
            if not isinstance(binding_id, str) or not binding_id:
                raise BindingRegistryError(
                    f"Official defaults file '{self._safe_relpath(path)}' contains an invalid binding id for capability '{capability_id}'."
                )
            normalized[capability_id] = binding_id

        self._official_defaults = normalized

    def _validate_references(self) -> None:
        for binding in self._bindings_by_id.values():
            if binding.service_id not in self._services_by_id:
                raise BindingRegistryError(
                    f"Binding '{binding.id}' references unknown service '{binding.service_id}'."
                )

        for capability_id, binding_id in self._official_defaults.items():
            binding = self._bindings_by_id.get(binding_id)
            if binding is None:
                raise BindingRegistryError(
                    f"Official default for capability '{capability_id}' references unknown binding '{binding_id}'."
                )
            if binding.source != "official":
                raise BindingRegistryError(
                    f"Official default for capability '{capability_id}' must reference an official binding, got '{binding_id}'."
                )
            if binding.capability_id != capability_id:
                raise BindingRegistryError(
                    f"Official default for capability '{capability_id}' points to binding '{binding_id}' for capability '{binding.capability_id}'."
                )

    def _register_service(self, service: ServiceDescriptor) -> None:
        existing = self._services_by_id.get(service.id)
        if existing is not None:
            raise BindingRegistryError(
                f"Duplicate service id '{service.id}' found in '{service.source_file}'."
            )
        self._services_by_id[service.id] = service

    def _register_binding(self, binding: BindingSpec) -> None:
        existing = self._bindings_by_id.get(binding.id)
        if existing is not None:
            raise BindingRegistryError(
                f"Duplicate binding id '{binding.id}' found in '{binding.source_file}'."
            )

        self._bindings_by_id[binding.id] = binding
        self._bindings_by_capability.setdefault(binding.capability_id, []).append(
            binding
        )

    def _load_service_file(self, path: Path, source: str) -> ServiceDescriptor:
        raw = self._read_yaml(path)
        if not isinstance(raw, dict):
            raise BindingRegistryError(
                f"Service file '{self._safe_relpath(path)}' must be a mapping."
            )

        service_id = raw.get("id")
        if not isinstance(service_id, str) or not service_id:
            raise BindingRegistryError(
                f"Service file '{self._safe_relpath(path)}' must define a non-empty string 'id'."
            )

        return self._normalize_service_entry(
            service_id=service_id,
            raw=raw,
            source=source,
            source_file=self._safe_relpath(path),
        )

    def _normalize_service_entry(
        self,
        service_id: str,
        raw: Any,
        source: str,
        source_file: str,
    ) -> ServiceDescriptor:
        if not isinstance(raw, dict):
            raise BindingRegistryError(
                f"Service '{service_id}' in '{source_file}' must be a mapping."
            )

        kind = raw.get("kind")
        if not isinstance(kind, str) or not kind:
            raise BindingRegistryError(
                f"Service '{service_id}' in '{source_file}' must define a non-empty string 'kind'."
            )

        if kind not in {"openapi", "mcp", "openrpc", "pythoncall"}:
            raise BindingRegistryError(
                f"Service '{service_id}' in '{source_file}' has unsupported kind '{kind}'."
            )

        spec_ref = self._optional_string(
            raw.get("spec_ref"), "spec_ref", service_id, source_file
        )
        auth_ref = self._optional_string(
            raw.get("auth_ref"), "auth_ref", service_id, source_file
        )
        base_url = self._optional_string(
            raw.get("base_url"), "base_url", service_id, source_file
        )
        server = self._optional_string(
            raw.get("server"), "server", service_id, source_file
        )
        module = self._optional_string(
            raw.get("module"), "module", service_id, source_file
        )

        metadata = raw.get("metadata", {})
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise BindingRegistryError(
                f"Service '{service_id}' in '{source_file}' field 'metadata' must be a mapping if present."
            )

        self._validate_service_shape(
            service_id=service_id,
            kind=kind,
            spec_ref=spec_ref,
            base_url=base_url,
            server=server,
            module=module,
            source_file=source_file,
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
            source=source,
            source_file=source_file,
        )

    def _validate_service_shape(
        self,
        *,
        service_id: str,
        kind: str,
        spec_ref: str | None,
        base_url: str | None,
        server: str | None,
        module: str | None,
        source_file: str,
    ) -> None:
        if kind in {"openapi", "openrpc"}:
            if spec_ref is None and base_url is None:
                raise BindingRegistryError(
                    f"Service '{service_id}' in '{source_file}' must define at least one of 'spec_ref' or 'base_url' for kind '{kind}'."
                )
            if server is not None or module is not None:
                raise BindingRegistryError(
                    f"Service '{service_id}' in '{source_file}' uses unsupported fields for kind '{kind}'."
                )

        elif kind == "mcp":
            if server is None:
                raise BindingRegistryError(
                    f"Service '{service_id}' in '{source_file}' must define 'server' for kind 'mcp'."
                )
            if spec_ref is not None or base_url is not None or module is not None:
                raise BindingRegistryError(
                    f"Service '{service_id}' in '{source_file}' uses unsupported fields for kind 'mcp'."
                )

        elif kind == "pythoncall":
            if module is None:
                raise BindingRegistryError(
                    f"Service '{service_id}' in '{source_file}' must define 'module' for kind 'pythoncall'."
                )
            if spec_ref is not None or base_url is not None or server is not None:
                raise BindingRegistryError(
                    f"Service '{service_id}' in '{source_file}' uses unsupported fields for kind 'pythoncall'."
                )

    def _load_binding_file(self, path: Path, source: str) -> BindingSpec:
        raw = self._read_yaml(path)
        if not isinstance(raw, dict):
            raise BindingRegistryError(
                f"Binding file '{self._safe_relpath(path)}' must be a mapping."
            )

        relpath = self._safe_relpath(path)

        binding_id = raw.get("id")
        capability_id = raw.get("capability")
        service_id = raw.get("service")
        protocol = raw.get("protocol")
        operation_id = raw.get("operation")
        request_template = raw.get("request")
        response_mapping = raw.get("response")
        metadata = raw.get("metadata", {})

        if not isinstance(binding_id, str) or not binding_id:
            raise BindingRegistryError(
                f"Binding file '{relpath}' must define a non-empty string 'id'."
            )
        if not isinstance(capability_id, str) or not capability_id:
            raise BindingRegistryError(
                f"Binding '{binding_id}' in '{relpath}' must define a non-empty string 'capability'."
            )
        if not isinstance(service_id, str) or not service_id:
            raise BindingRegistryError(
                f"Binding '{binding_id}' in '{relpath}' must define a non-empty string 'service'."
            )
        if not isinstance(protocol, str) or not protocol:
            raise BindingRegistryError(
                f"Binding '{binding_id}' in '{relpath}' must define a non-empty string 'protocol'."
            )
        if protocol not in {"openapi", "mcp", "openrpc", "pythoncall"}:
            raise BindingRegistryError(
                f"Binding '{binding_id}' in '{relpath}' has unsupported protocol '{protocol}'."
            )
        if not isinstance(operation_id, str) or not operation_id:
            raise BindingRegistryError(
                f"Binding '{binding_id}' in '{relpath}' must define a non-empty string 'operation'."
            )
        if not isinstance(request_template, dict):
            raise BindingRegistryError(
                f"Binding '{binding_id}' in '{relpath}' field 'request' must be a mapping."
            )
        if not isinstance(response_mapping, dict):
            raise BindingRegistryError(
                f"Binding '{binding_id}' in '{relpath}' field 'response' must be a mapping."
            )
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise BindingRegistryError(
                f"Binding '{binding_id}' in '{relpath}' field 'metadata' must be a mapping if present."
            )

        conformance_profile = metadata.get("conformance_profile")
        if conformance_profile is not None:
            if not isinstance(conformance_profile, str) or not conformance_profile:
                raise BindingRegistryError(
                    f"Binding '{binding_id}' in '{relpath}' metadata.conformance_profile must be a non-empty string if present."
                )
            if conformance_profile not in self._allowed_conformance_profiles:
                allowed = ", ".join(sorted(self._allowed_conformance_profiles))
                raise BindingRegistryError(
                    f"Binding '{binding_id}' in '{relpath}' has invalid metadata.conformance_profile '{conformance_profile}'. Allowed values: {allowed}."
                )

        normalized_response_mapping: dict[str, str] = {}
        for output_name, response_ref in response_mapping.items():
            if not isinstance(output_name, str) or not output_name:
                raise BindingRegistryError(
                    f"Binding '{binding_id}' in '{relpath}' has an invalid response output name."
                )
            if not isinstance(response_ref, str) or not response_ref:
                raise BindingRegistryError(
                    f"Binding '{binding_id}' in '{relpath}' response mapping for '{output_name}' must be a non-empty string."
                )
            normalized_response_mapping[output_name] = response_ref

        return BindingSpec(
            id=binding_id,
            capability_id=capability_id,
            service_id=service_id,
            protocol=protocol,
            operation_id=operation_id,
            request_template=dict(request_template),
            response_mapping=normalized_response_mapping,
            metadata=dict(metadata),
            source=source,
            source_file=relpath,
        )

    def _read_yaml(self, path: Path) -> Any:
        try:
            with path.open("r", encoding="utf-8-sig") as f:
                return yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise BindingRegistryError(
                f"File '{self._safe_relpath(path)}' contains invalid YAML.",
                cause=e,
            ) from e
        except OSError as e:
            raise BindingRegistryError(
                f"File '{self._safe_relpath(path)}' could not be read.",
                cause=e,
            ) from e

    def _optional_string(
        self,
        value: Any,
        field_name: str,
        object_id: str,
        source_file: str,
    ) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value:
            raise BindingRegistryError(
                f"Object '{object_id}' in '{source_file}' field '{field_name}' must be a non-empty string if present."
            )
        return value

    def _safe_relpath(self, path: Path) -> str:
        try:
            return path.relative_to(self.repo_root).as_posix()
        except ValueError:
            if self.host_root is not None:
                host_agent_skills = self.host_root / ".agent-skills"
                try:
                    return path.relative_to(host_agent_skills).as_posix()
                except ValueError:
                    pass
            return path.as_posix()
