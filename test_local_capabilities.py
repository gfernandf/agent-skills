"""Tests for K8: Local Capabilities + Capability Extends.

Run: python -m pytest test_local_capabilities.py -v
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from runtime.capability_loader import YamlCapabilityLoader
from runtime.composite_capability_loader import CompositeCapabilityLoader
from runtime.errors import CapabilityNotFoundError, InvalidCapabilitySpecError
from runtime.models import CapabilitySpec, FieldSpec


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _write_cap(caps_dir: Path, cap: dict) -> Path:
    """Write a capability YAML to a capabilities/ directory and return path."""
    cap_id = cap["id"]
    filename = f"{cap_id}.yaml"
    path = caps_dir / filename
    path.write_text(yaml.dump(cap, default_flow_style=False), encoding="utf-8")
    return path


def _base_cap(cap_id: str = "test.base.cap", **overrides) -> dict:
    """Minimal valid capability dict."""
    cap = {
        "id": cap_id,
        "version": "1.0.0",
        "description": f"Test capability {cap_id}",
        "inputs": {
            "text": {"type": "string", "required": True},
            "max_length": {"type": "integer", "required": False},
        },
        "outputs": {
            "result": {"type": "string"},
        },
    }
    cap.update(overrides)
    return cap


# ═══════════════════════════════════════════════════════════════════════════
# YamlCapabilityLoader — basic functionality
# ═══════════════════════════════════════════════════════════════════════════


class TestYamlCapabilityLoader:
    """Verify that the loader correctly parses capabilities including the
    new 'extends' field."""

    def test_load_standard_cap(self, tmp_path):
        caps_dir = tmp_path / "capabilities"
        caps_dir.mkdir()
        _write_cap(caps_dir, _base_cap())

        loader = YamlCapabilityLoader(tmp_path)
        cap = loader.get_capability("test.base.cap")

        assert cap.id == "test.base.cap"
        assert cap.version == "1.0.0"
        assert "text" in cap.inputs
        assert cap.inputs["text"].required is True
        assert cap.extends is None

    def test_load_cap_with_extends_field(self, tmp_path):
        caps_dir = tmp_path / "capabilities"
        caps_dir.mkdir()
        ext_cap = _base_cap(
            cap_id="local.extended",
            extends="test.base.cap",
        )
        # When extending, inputs/outputs are optional — test with partial
        ext_cap["inputs"] = {
            "format": {"type": "string", "required": False},
        }
        del ext_cap["outputs"]
        _write_cap(caps_dir, ext_cap)

        loader = YamlCapabilityLoader(tmp_path)
        cap = loader.get_capability("local.extended")

        assert cap.extends == "test.base.cap"
        # Only the locally declared inputs — base merge happens in Composite
        assert "format" in cap.inputs
        assert "text" not in cap.inputs  # not merged yet
        assert cap.outputs == {}

    def test_extends_allows_empty_inputs_outputs(self, tmp_path):
        """When extends is set, both inputs and outputs may be omitted."""
        caps_dir = tmp_path / "capabilities"
        caps_dir.mkdir()
        ext_cap = {
            "id": "local.minimal_extend",
            "version": "1.0.0",
            "description": "Pure extension, no new fields",
            "extends": "some.base",
        }
        _write_cap(caps_dir, ext_cap)

        loader = YamlCapabilityLoader(tmp_path)
        cap = loader.get_capability("local.minimal_extend")
        assert cap.extends == "some.base"
        assert cap.inputs == {}
        assert cap.outputs == {}

    def test_get_all_capabilities(self, tmp_path):
        caps_dir = tmp_path / "capabilities"
        caps_dir.mkdir()
        _write_cap(caps_dir, _base_cap("cap.one"))
        _write_cap(caps_dir, _base_cap("cap.two"))

        loader = YamlCapabilityLoader(tmp_path)
        all_caps = loader.get_all_capabilities()
        assert "cap.one" in all_caps
        assert "cap.two" in all_caps

    def test_not_found_raises(self, tmp_path):
        caps_dir = tmp_path / "capabilities"
        caps_dir.mkdir()
        loader = YamlCapabilityLoader(tmp_path)

        with pytest.raises(CapabilityNotFoundError):
            loader.get_capability("does.not.exist")


# ═══════════════════════════════════════════════════════════════════════════
# CompositeCapabilityLoader — local priority
# ═══════════════════════════════════════════════════════════════════════════


class TestCompositeLocalPriority:
    """Local capabilities take precedence over registry ones."""

    def test_local_cap_found_over_registry(self, tmp_path):
        reg = tmp_path / "registry" / "capabilities"
        reg.mkdir(parents=True)
        local = tmp_path / "local" / "capabilities"
        local.mkdir(parents=True)

        _write_cap(reg, _base_cap("shared.cap", description="registry version"))
        _write_cap(local, _base_cap("shared.cap", description="local version"))

        reg_loader = YamlCapabilityLoader(tmp_path / "registry")
        local_loader = YamlCapabilityLoader(tmp_path / "local")
        composite = CompositeCapabilityLoader([local_loader, reg_loader])

        cap = composite.get_capability("shared.cap")
        assert cap.description == "local version"

    def test_falls_through_to_registry(self, tmp_path):
        reg = tmp_path / "registry" / "capabilities"
        reg.mkdir(parents=True)
        local = tmp_path / "local" / "capabilities"
        local.mkdir(parents=True)

        _write_cap(reg, _base_cap("registry.only"))

        reg_loader = YamlCapabilityLoader(tmp_path / "registry")
        local_loader = YamlCapabilityLoader(tmp_path / "local")
        composite = CompositeCapabilityLoader([local_loader, reg_loader])

        cap = composite.get_capability("registry.only")
        assert cap.id == "registry.only"

    def test_local_only_cap(self, tmp_path):
        reg = tmp_path / "registry" / "capabilities"
        reg.mkdir(parents=True)
        local = tmp_path / "local" / "capabilities"
        local.mkdir(parents=True)

        _write_cap(local, _base_cap("local.custom.cap"))

        reg_loader = YamlCapabilityLoader(tmp_path / "registry")
        local_loader = YamlCapabilityLoader(tmp_path / "local")
        composite = CompositeCapabilityLoader([local_loader, reg_loader])

        cap = composite.get_capability("local.custom.cap")
        assert cap.id == "local.custom.cap"

    def test_not_found_in_any_raises(self, tmp_path):
        reg = tmp_path / "registry" / "capabilities"
        reg.mkdir(parents=True)
        local = tmp_path / "local" / "capabilities"
        local.mkdir(parents=True)

        reg_loader = YamlCapabilityLoader(tmp_path / "registry")
        local_loader = YamlCapabilityLoader(tmp_path / "local")
        composite = CompositeCapabilityLoader([local_loader, reg_loader])

        with pytest.raises(CapabilityNotFoundError, match="not found"):
            composite.get_capability("ghost.cap")

    def test_get_all_capabilities_union(self, tmp_path):
        reg = tmp_path / "registry" / "capabilities"
        reg.mkdir(parents=True)
        local = tmp_path / "local" / "capabilities"
        local.mkdir(parents=True)

        _write_cap(reg, _base_cap("cap.reg"))
        _write_cap(local, _base_cap("cap.local"))
        _write_cap(reg, _base_cap("cap.shared", description="reg"))
        _write_cap(local, _base_cap("cap.shared", description="local"))

        reg_loader = YamlCapabilityLoader(tmp_path / "registry")
        local_loader = YamlCapabilityLoader(tmp_path / "local")
        composite = CompositeCapabilityLoader([local_loader, reg_loader])

        all_caps = composite.get_all_capabilities()
        assert "cap.reg" in all_caps
        assert "cap.local" in all_caps
        assert "cap.shared" in all_caps
        assert all_caps["cap.shared"].description == "local"

    def test_empty_loaders_raises(self):
        with pytest.raises(ValueError, match="at least one"):
            CompositeCapabilityLoader([])


# ═══════════════════════════════════════════════════════════════════════════
# CompositeCapabilityLoader — extends resolution
# ═══════════════════════════════════════════════════════════════════════════


class TestCapabilityExtends:
    """Validate the extends/inheritance mechanism."""

    def test_extends_inherits_base_inputs(self, tmp_path):
        reg = tmp_path / "registry" / "capabilities"
        reg.mkdir(parents=True)
        local = tmp_path / "local" / "capabilities"
        local.mkdir(parents=True)

        # Base in registry
        _write_cap(reg, _base_cap("text.content.summarize"))

        # Extension in local — adds 'format' input
        ext = {
            "id": "local.text.content.summarize_v2",
            "version": "1.0.0",
            "description": "Extended summarization with format control",
            "extends": "text.content.summarize",
            "inputs": {
                "format": {"type": "string", "required": False},
            },
            "outputs": {
                "keywords": {"type": "string", "required": False},
            },
        }
        _write_cap(local, ext)

        reg_loader = YamlCapabilityLoader(tmp_path / "registry")
        local_loader = YamlCapabilityLoader(tmp_path / "local")
        composite = CompositeCapabilityLoader([local_loader, reg_loader])

        resolved = composite.get_capability("local.text.content.summarize_v2")

        # Base inputs inherited
        assert "text" in resolved.inputs
        assert resolved.inputs["text"].required is True
        assert "max_length" in resolved.inputs
        # Extension input added
        assert "format" in resolved.inputs
        assert resolved.inputs["format"].required is False
        # Base output inherited
        assert "result" in resolved.outputs
        # Extension output added
        assert "keywords" in resolved.outputs

    def test_extends_only_description_override(self, tmp_path):
        """Extension with no new fields — just a re-description of base."""
        reg = tmp_path / "registry" / "capabilities"
        reg.mkdir(parents=True)
        local = tmp_path / "local" / "capabilities"
        local.mkdir(parents=True)

        _write_cap(reg, _base_cap("base.cap"))
        ext = {
            "id": "local.alias",
            "version": "2.0.0",
            "description": "Same contract, different name",
            "extends": "base.cap",
        }
        _write_cap(local, ext)

        composite = CompositeCapabilityLoader([
            YamlCapabilityLoader(tmp_path / "local"),
            YamlCapabilityLoader(tmp_path / "registry"),
        ])
        resolved = composite.get_capability("local.alias")

        assert resolved.id == "local.alias"
        assert resolved.description == "Same contract, different name"
        assert resolved.inputs == _make_base_fields()["inputs"]
        assert resolved.outputs == _make_base_fields()["outputs"]

    def test_extends_cannot_weaken_required_input(self, tmp_path):
        """Extension cannot make a base-required field optional."""
        reg = tmp_path / "registry" / "capabilities"
        reg.mkdir(parents=True)
        local = tmp_path / "local" / "capabilities"
        local.mkdir(parents=True)

        _write_cap(reg, _base_cap("strict.base"))
        ext = {
            "id": "local.weakened",
            "version": "1.0.0",
            "description": "Tries to weaken 'text' from required to optional",
            "extends": "strict.base",
            "inputs": {
                "text": {"type": "string", "required": False},
            },
            "outputs": {},
        }
        _write_cap(local, ext)

        composite = CompositeCapabilityLoader([
            YamlCapabilityLoader(tmp_path / "local"),
            YamlCapabilityLoader(tmp_path / "registry"),
        ])

        with pytest.raises(InvalidCapabilitySpecError, match="cannot weaken"):
            composite.get_capability("local.weakened")

    def test_extends_can_strengthen_optional_to_required(self, tmp_path):
        """Extension CAN make an optional field required (strengthening)."""
        reg = tmp_path / "registry" / "capabilities"
        reg.mkdir(parents=True)
        local = tmp_path / "local" / "capabilities"
        local.mkdir(parents=True)

        _write_cap(reg, _base_cap("base.opt"))
        ext = {
            "id": "local.stronger",
            "version": "1.0.0",
            "description": "Makes max_length required",
            "extends": "base.opt",
            "inputs": {
                "max_length": {"type": "integer", "required": True},
            },
            "outputs": {},
        }
        _write_cap(local, ext)

        composite = CompositeCapabilityLoader([
            YamlCapabilityLoader(tmp_path / "local"),
            YamlCapabilityLoader(tmp_path / "registry"),
        ])
        resolved = composite.get_capability("local.stronger")

        assert resolved.inputs["max_length"].required is True
        assert resolved.inputs["text"].required is True  # inherited

    def test_extends_chain_a_extends_b_extends_c(self, tmp_path):
        """Multi-level extends chain is resolved recursively."""
        caps = tmp_path / "all" / "capabilities"
        caps.mkdir(parents=True)

        # C (base)
        _write_cap(caps, _base_cap("level.c"))
        # B extends C — adds 'language'
        _write_cap(caps, {
            "id": "level.b",
            "version": "1.0.0",
            "description": "Level B extends C",
            "extends": "level.c",
            "inputs": {"language": {"type": "string", "required": False}},
        })
        # A extends B — adds 'style'
        _write_cap(caps, {
            "id": "level.a",
            "version": "1.0.0",
            "description": "Level A extends B",
            "extends": "level.b",
            "inputs": {"style": {"type": "string", "required": False}},
        })

        composite = CompositeCapabilityLoader([
            YamlCapabilityLoader(tmp_path / "all"),
        ])
        resolved = composite.get_capability("level.a")

        # Has C's inputs + B's + A's
        assert "text" in resolved.inputs       # from C
        assert "max_length" in resolved.inputs  # from C
        assert "language" in resolved.inputs    # from B
        assert "style" in resolved.inputs       # from A
        assert "result" in resolved.outputs     # from C

    def test_extends_cycle_detected(self, tmp_path):
        """Circular extends chain raises an error."""
        caps = tmp_path / "cycle" / "capabilities"
        caps.mkdir(parents=True)

        _write_cap(caps, {
            "id": "cycle.a",
            "version": "1.0.0",
            "description": "A extends B",
            "extends": "cycle.b",
            "inputs": {"x": {"type": "string", "required": False}},
            "outputs": {"y": {"type": "string"}},
        })
        _write_cap(caps, {
            "id": "cycle.b",
            "version": "1.0.0",
            "description": "B extends A",
            "extends": "cycle.a",
            "inputs": {"x": {"type": "string", "required": False}},
            "outputs": {"y": {"type": "string"}},
        })

        composite = CompositeCapabilityLoader([
            YamlCapabilityLoader(tmp_path / "cycle"),
        ])

        with pytest.raises(InvalidCapabilitySpecError, match="depth"):
            composite.get_capability("cycle.a")

    def test_extends_inherits_properties(self, tmp_path):
        reg = tmp_path / "registry" / "capabilities"
        reg.mkdir(parents=True)
        local = tmp_path / "local" / "capabilities"
        local.mkdir(parents=True)

        base = _base_cap("prop.base")
        base["properties"] = {"deterministic": True, "side_effects": False}
        _write_cap(reg, base)

        ext = {
            "id": "prop.ext",
            "version": "1.0.0",
            "description": "Adds side_effects override",
            "extends": "prop.base",
            "properties": {"side_effects": True, "idempotent": True},
        }
        _write_cap(local, ext)

        composite = CompositeCapabilityLoader([
            YamlCapabilityLoader(tmp_path / "local"),
            YamlCapabilityLoader(tmp_path / "registry"),
        ])
        resolved = composite.get_capability("prop.ext")

        assert resolved.properties["deterministic"] is True   # inherited
        assert resolved.properties["side_effects"] is True     # overridden
        assert resolved.properties["idempotent"] is True       # added

    def test_extends_inherits_cognitive_hints(self, tmp_path):
        reg = tmp_path / "registry" / "capabilities"
        reg.mkdir(parents=True)
        local = tmp_path / "local" / "capabilities"
        local.mkdir(parents=True)

        base = _base_cap("cog.base")
        base["cognitive_hints"] = {"role": "synthesize", "consumes": ["Context"]}
        _write_cap(reg, base)

        ext = {
            "id": "cog.ext",
            "version": "1.0.0",
            "description": "No cognitive_hints — inherits from base",
            "extends": "cog.base",
        }
        _write_cap(local, ext)

        composite = CompositeCapabilityLoader([
            YamlCapabilityLoader(tmp_path / "local"),
            YamlCapabilityLoader(tmp_path / "registry"),
        ])
        resolved = composite.get_capability("cog.ext")

        assert resolved.cognitive_hints is not None
        assert "role" in resolved.cognitive_hints

    def test_extends_base_not_found_raises(self, tmp_path):
        local = tmp_path / "local" / "capabilities"
        local.mkdir(parents=True)

        ext = {
            "id": "orphan.ext",
            "version": "1.0.0",
            "description": "Extends a non-existent base",
            "extends": "ghost.base",
        }
        _write_cap(local, ext)

        composite = CompositeCapabilityLoader([
            YamlCapabilityLoader(tmp_path / "local"),
        ])

        with pytest.raises(CapabilityNotFoundError, match="ghost.base"):
            composite.get_capability("orphan.ext")

    def test_extends_cross_loader_local_extends_registry(self, tmp_path):
        """Local capability can extend a registry-only capability."""
        reg = tmp_path / "registry" / "capabilities"
        reg.mkdir(parents=True)
        local = tmp_path / "local" / "capabilities"
        local.mkdir(parents=True)

        _write_cap(reg, _base_cap("registry.base"))
        ext = {
            "id": "local.extended_from_registry",
            "version": "1.0.0",
            "description": "Local extends registry cap",
            "extends": "registry.base",
            "inputs": {"extra": {"type": "string", "required": False}},
        }
        _write_cap(local, ext)

        composite = CompositeCapabilityLoader([
            YamlCapabilityLoader(tmp_path / "local"),
            YamlCapabilityLoader(tmp_path / "registry"),
        ])
        resolved = composite.get_capability("local.extended_from_registry")

        assert "text" in resolved.inputs      # from registry base
        assert "extra" in resolved.inputs     # from local extension
        assert resolved.extends == "registry.base"


# ═══════════════════════════════════════════════════════════════════════════
# Engine factory integration
# ═══════════════════════════════════════════════════════════════════════════


class TestEngineFactoryLocalCaps:
    """Verify that build_runtime_components detects local capabilities."""

    def test_composite_loader_when_local_caps_exist(self, tmp_path):
        """When .agent-skills/capabilities/ exists, factory uses CompositeCapabilityLoader."""
        registry = tmp_path / "registry"
        runtime = tmp_path / "runtime"
        host = tmp_path / "host"

        (registry / "capabilities").mkdir(parents=True)
        (registry / "skills").mkdir(parents=True)
        (runtime / "skills" / "local").mkdir(parents=True)
        (host / ".agent-skills" / "capabilities").mkdir(parents=True)

        # Write a local cap
        _write_cap(
            host / ".agent-skills" / "capabilities",
            _base_cap("local.my.custom.cap"),
        )
        # Write a registry cap
        _write_cap(
            registry / "capabilities",
            _base_cap("registry.standard.cap"),
        )

        from runtime.engine_factory import build_runtime_components
        from runtime.composite_capability_loader import CompositeCapabilityLoader

        components = build_runtime_components(registry, runtime, host)

        assert isinstance(components.capability_loader, CompositeCapabilityLoader)

        # Both caps accessible
        local_cap = components.capability_loader.get_capability("local.my.custom.cap")
        assert local_cap.id == "local.my.custom.cap"

        reg_cap = components.capability_loader.get_capability("registry.standard.cap")
        assert reg_cap.id == "registry.standard.cap"

    def test_plain_loader_when_no_local_caps(self, tmp_path):
        """When .agent-skills/capabilities/ doesn't exist, factory uses YamlCapabilityLoader."""
        registry = tmp_path / "registry"
        runtime = tmp_path / "runtime"
        host = tmp_path / "host"

        (registry / "capabilities").mkdir(parents=True)
        (registry / "skills").mkdir(parents=True)
        host.mkdir(parents=True)

        _write_cap(registry / "capabilities", _base_cap("reg.cap"))

        from runtime.engine_factory import build_runtime_components

        components = build_runtime_components(registry, runtime, host)
        assert isinstance(components.capability_loader, YamlCapabilityLoader)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers for expected field structures
# ═══════════════════════════════════════════════════════════════════════════


def _make_base_fields():
    """Return the expected FieldSpec dicts for _base_cap()."""
    return {
        "inputs": {
            "text": FieldSpec(type="string", required=True),
            "max_length": FieldSpec(type="integer", required=False),
        },
        "outputs": {
            "result": FieldSpec(type="string", required=False),
        },
    }
