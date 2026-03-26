"""
Tests for cognitive_hints: loader, auto-wire mapping, and consumes chain validation.
"""

from __future__ import annotations

import sys
import textwrap
import tempfile
from pathlib import Path
from typing import Any

from runtime.models import CapabilitySpec, FieldSpec, StepSpec, SkillSpec
from runtime.execution_planner import validate_consumes_chain

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_pass = 0
_fail = 0


def _test(label: str, condition: bool, detail: str = "") -> None:
    global _pass, _fail
    if condition:
        _pass += 1
    else:
        _fail += 1
        msg = f"  FAIL: {label}"
        if detail:
            msg += f" — {detail}"
        print(msg)


def _make_cap(
    id: str,
    cognitive_hints: dict[str, Any] | None = None,
    outputs: dict[str, FieldSpec] | None = None,
) -> CapabilitySpec:
    return CapabilitySpec(
        id=id,
        version="1.0.0",
        description="test",
        inputs={},
        outputs=outputs or {},
        metadata={},
        properties={},
        cognitive_hints=cognitive_hints,
    )


def _make_step(
    id: str, uses: str, output_mapping: dict[str, str] | None = None
) -> StepSpec:
    return StepSpec(
        id=id, uses=uses, input_mapping={}, output_mapping=output_mapping or {}
    )


class _FakeCapLoader:
    def __init__(self, caps: dict[str, CapabilitySpec]):
        self._caps = caps

    def get_capability(self, cid: str) -> CapabilitySpec:
        if cid not in self._caps:
            raise KeyError(cid)
        return self._caps[cid]


# ---------------------------------------------------------------------------
# 1. CapabilitySpec cognitive_hints field
# ---------------------------------------------------------------------------


def test_capability_spec_cognitive_hints():
    print("▸ CapabilitySpec cognitive_hints field")

    cap = _make_cap("test.cap")
    _test("default is None", cap.cognitive_hints is None)

    hints = {"role": ["analyze"], "produces": {"risks": {"type": "Risk"}}}
    cap2 = _make_cap("test.cap2", cognitive_hints=hints)
    _test("set via constructor", cap2.cognitive_hints == hints)
    _test("role is list", cap2.cognitive_hints["role"] == ["analyze"])


# ---------------------------------------------------------------------------
# 2. YamlCapabilityLoader cognitive_hints normalization
# ---------------------------------------------------------------------------


def test_loader_normalization():
    print("▸ YamlCapabilityLoader cognitive_hints normalization")

    from runtime.capability_loader import YamlCapabilityLoader

    # Create a temporary registry with a single capability
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        cap_dir = root / "capabilities"
        cap_dir.mkdir()

        # Capability with cognitive_hints
        (cap_dir / "test.cap.hint.yaml").write_text(
            textwrap.dedent("""\
            id: test.cap.hint
            version: 1.0.0
            description: test cap with hints

            inputs:
              x:
                type: string
                required: true

            outputs:
              result:
                type: string

            cognitive_hints:
              role: analyze
              consumes:
                - Context
              produces:
                result:
                  type: Summary
        """),
            encoding="utf-8",
        )

        # Capability without cognitive_hints
        (cap_dir / "test.cap.plain.yaml").write_text(
            textwrap.dedent("""\
            id: test.cap.plain
            version: 1.0.0
            description: test cap without hints

            inputs:
              x:
                type: string
                required: true

            outputs:
              result:
                type: string
        """),
            encoding="utf-8",
        )

        loader = YamlCapabilityLoader(root)

        cap_hint = loader.get_capability("test.cap.hint")
        _test("hints loaded", cap_hint.cognitive_hints is not None)
        _test(
            "role normalized to list", cap_hint.cognitive_hints["role"] == ["analyze"]
        )
        _test("consumes preserved", cap_hint.cognitive_hints["consumes"] == ["Context"])
        _test("produces preserved", "result" in cap_hint.cognitive_hints["produces"])
        _test(
            "produces type",
            cap_hint.cognitive_hints["produces"]["result"]["type"] == "Summary",
        )

        cap_plain = loader.get_capability("test.cap.plain")
        _test("no hints → None", cap_plain.cognitive_hints is None)


def test_loader_cognitive_types():
    print("▸ YamlCapabilityLoader get_cognitive_types")

    from runtime.capability_loader import YamlCapabilityLoader

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "capabilities").mkdir()

        # No vocabulary file → empty dict
        loader = YamlCapabilityLoader(root)
        ct = loader.get_cognitive_types()
        _test("missing vocab → empty dict", ct == {})

        # With vocabulary file
        vocab_dir = root / "vocabulary"
        vocab_dir.mkdir()
        (vocab_dir / "cognitive_types.yaml").write_text(
            textwrap.dedent("""\
            version: 0.1.0
            types:
              Risk:
                default_slot: working.risks
                cardinality: list
              Summary:
                default_slot: output.summary
                cardinality: single
            roles:
              - analyze
              - synthesize
        """),
            encoding="utf-8",
        )

        loader2 = YamlCapabilityLoader(root)
        ct2 = loader2.get_cognitive_types()
        _test("types loaded", "Risk" in ct2.get("types", {}))
        _test("roles loaded", "analyze" in ct2.get("roles", []))
        _test("cached on second call", loader2.get_cognitive_types() is ct2)


# ---------------------------------------------------------------------------
# 3. _build_auto_wire_mapping
# ---------------------------------------------------------------------------


def test_auto_wire_mapping():
    print("▸ _build_auto_wire_mapping")

    from runtime.execution_engine import _build_auto_wire_mapping

    cognitive_types = {
        "types": {
            "Risk": {"default_slot": "working.risks", "cardinality": "list"},
            "Summary": {"default_slot": "output.summary", "cardinality": "single"},
            "Artifact": {"default_slot": "working.artifacts", "cardinality": "keyed"},
        }
    }

    # Capability without hints → None
    cap_no_hints = _make_cap("noop")
    _test(
        "no hints → None",
        _build_auto_wire_mapping(cap_no_hints, cognitive_types) is None,
    )

    # Capability with produces using default slots
    cap_risk = _make_cap(
        "risk.extract",
        cognitive_hints={
            "role": ["analyze"],
            "produces": {
                "risks": {"type": "Risk"},
                "summary": {"type": "Summary"},
            },
        },
    )
    mapping = _build_auto_wire_mapping(cap_risk, cognitive_types)
    _test("mapping not None", mapping is not None)
    _test("risks → default slot", mapping["risks"] == "working.risks")
    _test("summary → default slot", mapping["summary"] == "output.summary")

    # Produces with target override
    cap_override = _make_cap(
        "custom",
        cognitive_hints={
            "role": ["synthesize"],
            "produces": {
                "result": {"type": "Summary", "target": "output.custom_summary"},
            },
        },
    )
    mapping2 = _build_auto_wire_mapping(cap_override, cognitive_types)
    _test("target override used", mapping2["result"] == "output.custom_summary")

    # Unknown type (no default_slot) → skipped
    cap_unknown = _make_cap(
        "unk",
        cognitive_hints={
            "role": ["analyze"],
            "produces": {
                "data": {"type": "UnknownType"},
            },
        },
    )
    mapping3 = _build_auto_wire_mapping(cap_unknown, cognitive_types)
    _test("unknown type → None mapping", mapping3 is None)


# ---------------------------------------------------------------------------
# 4. validate_consumes_chain
# ---------------------------------------------------------------------------


def test_consumes_chain_valid():
    print("▸ validate_consumes_chain — valid chain")

    caps = {
        "web.page.fetch": _make_cap(
            "web.page.fetch",
            cognitive_hints={
                "role": ["perceive"],
                "produces": {"content": {"type": "Artifact"}},
            },
        ),
        "text.content.summarize": _make_cap(
            "text.content.summarize",
            cognitive_hints={
                "role": ["synthesize"],
                "consumes": ["Artifact"],
                "produces": {"summary": {"type": "Summary"}},
            },
        ),
    }
    loader = _FakeCapLoader(caps)

    steps = (
        _make_step("fetch", "web.page.fetch"),
        _make_step("summarize", "text.content.summarize"),
    )

    warnings = validate_consumes_chain(steps, loader)
    _test("no warnings for valid chain", len(warnings) == 0)


def test_consumes_chain_missing():
    print("▸ validate_consumes_chain — missing upstream type")

    caps = {
        "text.content.summarize": _make_cap(
            "text.content.summarize",
            cognitive_hints={
                "role": ["synthesize"],
                "consumes": ["Artifact"],
                "produces": {"summary": {"type": "Summary"}},
            },
        ),
    }
    loader = _FakeCapLoader(caps)

    steps = (_make_step("summarize", "text.content.summarize"),)

    warnings = validate_consumes_chain(steps, loader)
    _test("warning emitted", len(warnings) == 1)
    _test("mentions Artifact", "Artifact" in warnings[0])


def test_consumes_chain_skill_step_ignored():
    print("▸ validate_consumes_chain — skill: steps are ignored")

    caps = {
        "analysis.risk.extract": _make_cap(
            "analysis.risk.extract",
            cognitive_hints={
                "role": ["analyze"],
                "consumes": ["Artifact"],
                "produces": {"risks": {"type": "Risk"}},
            },
        ),
    }
    loader = _FakeCapLoader(caps)

    steps = (
        _make_step("nested", "skill:some.nested"),
        _make_step("extract", "analysis.risk.extract"),
    )

    warnings = validate_consumes_chain(steps, loader)
    _test("warning for Artifact (skill: doesn't produce types)", len(warnings) == 1)


def test_consumes_chain_no_hints():
    print("▸ validate_consumes_chain — caps without hints are transparent")

    caps = {
        "fs.file.read": _make_cap("fs.file.read"),
        "text.content.summarize": _make_cap(
            "text.content.summarize",
            cognitive_hints={
                "role": ["synthesize"],
                "consumes": ["Context"],
                "produces": {"summary": {"type": "Summary"}},
            },
        ),
    }
    loader = _FakeCapLoader(caps)

    steps = (
        _make_step("read", "fs.file.read"),
        _make_step("summarize", "text.content.summarize"),
    )

    warnings = validate_consumes_chain(steps, loader)
    _test("warning for Context (no upstream produces it)", len(warnings) == 1)


def test_consumes_chain_multi_step():
    print("▸ validate_consumes_chain — multi-step accumulation")

    caps = {
        "web.page.fetch": _make_cap(
            "web.page.fetch",
            cognitive_hints={
                "role": ["perceive"],
                "produces": {"content": {"type": "Artifact"}},
            },
        ),
        "analysis.risk.extract": _make_cap(
            "analysis.risk.extract",
            cognitive_hints={
                "role": ["analyze"],
                "consumes": ["Artifact"],
                "produces": {
                    "risks": {"type": "Risk"},
                    "assumptions": {"type": "Evidence"},
                },
            },
        ),
        "eval.option.score": _make_cap(
            "eval.option.score",
            cognitive_hints={
                "role": ["evaluate"],
                "consumes": ["Risk", "Evidence"],
                "produces": {"scored": {"type": "Score"}},
            },
        ),
    }
    loader = _FakeCapLoader(caps)

    steps = (
        _make_step("fetch", "web.page.fetch"),
        _make_step("extract", "analysis.risk.extract"),
        _make_step("score", "eval.option.score"),
    )

    warnings = validate_consumes_chain(steps, loader)
    _test("full chain valid — no warnings", len(warnings) == 0)


# ---------------------------------------------------------------------------
# 5. apply_step_output with mapping_override
# ---------------------------------------------------------------------------


def test_output_mapper_override():
    print("▸ apply_step_output with mapping_override")

    from runtime.output_mapper import apply_step_output
    from runtime.execution_state import create_execution_state

    skill = SkillSpec(
        id="test.skill",
        version="1.0.0",
        name="test",
        description="test",
        inputs={},
        outputs={"summary": FieldSpec(type="string")},
        steps=(),
        metadata={},
    )

    state = create_execution_state(skill, {})

    step = _make_step("s1", "text.content.summarize", output_mapping={})
    produced = {"summary": "hello world"}

    # With empty output_mapping, nothing should be written
    apply_step_output(step, produced, state)
    _test("empty mapping → nothing written", state.vars == {})

    # With mapping_override, values should be written
    apply_step_output(
        step, produced, state, mapping_override={"summary": "outputs.summary"}
    )
    _test("override writes to output", state.outputs.get("summary") == "hello world")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Cognitive Hints — Unit Tests")
    print("=" * 60)
    print()

    test_capability_spec_cognitive_hints()
    test_loader_normalization()
    test_loader_cognitive_types()
    test_auto_wire_mapping()
    test_consumes_chain_valid()
    test_consumes_chain_missing()
    test_consumes_chain_skill_step_ignored()
    test_consumes_chain_no_hints()
    test_consumes_chain_multi_step()
    test_output_mapper_override()

    print()
    print("=" * 60)
    print(f"Results: {_pass} passed, {_fail} failed")
    print("=" * 60)

    if _fail > 0:
        sys.exit(1)
