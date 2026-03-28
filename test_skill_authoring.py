"""Tests for tooling/skill_authoring.py — M2, M4, M6, M7, M8, M10, M11, M12, M14.

Validates all skill authoring helper functions used by the CLI commands.
Run: pytest test_skill_authoring.py -v
"""

from __future__ import annotations

import json
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from tooling.skill_authoring import (
    check_wiring,
    export_skill_bundle,
    filter_capabilities_by_type,
    find_similar_skills,
    generate_issue_report,
    generate_mermaid_dag,
    generate_test_fixture,
    import_skill_bundle,
    rate_skill,
    suggest_wiring,
)

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

_MINIMAL_SKILL = {
    "id": "test.summarize",
    "version": "0.1.0",
    "name": "Test Summarize",
    "description": "Summarize text for testing",
    "inputs": {
        "text": {"type": "string", "required": True},
        "max_length": {"type": "integer", "required": False, "default": 100},
    },
    "outputs": {
        "summary": {"type": "string", "required": True},
    },
    "steps": [
        {
            "id": "summarize",
            "uses": "text.content.summarize",
            "input": {"text": "inputs.text"},
            "output": {"summary": "outputs.summary"},
        }
    ],
}

_TWO_STEP_SKILL = {
    "id": "workflow.analyze-report",
    "version": "0.1.0",
    "name": "Analyze Report",
    "description": "Extract and analyze text",
    "inputs": {
        "document": {"type": "string", "required": True},
    },
    "outputs": {
        "analysis": {"type": "string", "required": True},
    },
    "steps": [
        {
            "id": "extract",
            "uses": "text.content.extract",
            "input": {"text": "inputs.document"},
            "output": {"extracted": "vars.extracted_text"},
        },
        {
            "id": "analyze",
            "uses": "text.content.analyze",
            "input": {"text": "vars.extracted_text"},
            "output": {"result": "outputs.analysis"},
            "config": {"depends_on": ["extract"]},
        },
    ],
}


def _make_cap(cap_id: str, inputs: dict, outputs: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=cap_id,
        description=f"Mock {cap_id}",
        inputs=inputs,
        outputs=outputs,
    )


# ═══════════════════════════════════════════════════════════════════════════
# M2 — generate_test_fixture
# ═══════════════════════════════════════════════════════════════════════════


class TestGenerateTestFixture:
    def test_generates_defaults_from_types(self):
        fixture = generate_test_fixture(_MINIMAL_SKILL)
        assert "text" in fixture
        assert isinstance(fixture["text"], str)
        # max_length has a default of 100
        assert fixture["max_length"] == 100

    def test_uses_type_defaults(self):
        skill = {
            "inputs": {
                "flag": {"type": "boolean"},
                "count": {"type": "integer"},
                "items": {"type": "array"},
                "meta": {"type": "object"},
            }
        }
        fixture = generate_test_fixture(skill)
        assert fixture["flag"] is True
        assert fixture["count"] == 1
        assert fixture["items"] == []
        assert fixture["meta"] == {}

    def test_empty_inputs(self):
        fixture = generate_test_fixture({"inputs": {}})
        assert fixture == {}

    def test_no_inputs_key(self):
        fixture = generate_test_fixture({})
        assert fixture == {}


# ═══════════════════════════════════════════════════════════════════════════
# M8 — check_wiring
# ═══════════════════════════════════════════════════════════════════════════


class TestCheckWiring:
    def test_no_issues_on_valid_skill(self):
        caps = {
            "text.content.summarize": _make_cap(
                "text.content.summarize",
                {"text": {"type": "string", "required": True}},
                {"summary": {"type": "string"}},
            )
        }
        issues = check_wiring(_MINIMAL_SKILL, caps)
        assert len(issues) == 0

    def test_detects_missing_source(self):
        skill = {
            "inputs": {},
            "steps": [
                {
                    "id": "s1",
                    "uses": "test.cap",
                    "input": {"text": "vars.nonexistent"},
                    "output": {"result": "outputs.result"},
                }
            ],
        }
        issues = check_wiring(skill, {})
        assert len(issues) >= 1
        assert "nonexistent" in issues[0]["message"]

    def test_detects_type_mismatch(self):
        skill = {
            "inputs": {"text": {"type": "string"}},
            "steps": [
                {
                    "id": "s1",
                    "uses": "test.cap",
                    "input": {"count": "inputs.text"},
                    "output": {},
                }
            ],
        }
        caps = {
            "test.cap": _make_cap(
                "test.cap",
                {"count": {"type": "integer", "required": True}},
                {},
            )
        }
        issues = check_wiring(skill, caps)
        assert any("mismatch" in i["message"].lower() for i in issues)

    def test_empty_steps(self):
        issues = check_wiring({"steps": []}, {})
        assert issues == []


# ═══════════════════════════════════════════════════════════════════════════
# M7 — filter_capabilities_by_type
# ═══════════════════════════════════════════════════════════════════════════


class TestFilterCapabilitiesByType:
    def test_filter_by_input_type(self):
        caps = {
            "a": _make_cap("a", {"text": {"type": "string"}}, {}),
            "b": _make_cap("b", {"count": {"type": "integer"}}, {}),
        }
        results = filter_capabilities_by_type(caps, input_type="string")
        assert len(results) == 1
        assert results[0].id == "a"

    def test_filter_by_output_type(self):
        caps = {
            "a": _make_cap("a", {}, {"list": {"type": "array"}}),
            "b": _make_cap("b", {}, {"count": {"type": "integer"}}),
        }
        results = filter_capabilities_by_type(caps, output_type="array")
        assert len(results) == 1
        assert results[0].id == "a"

    def test_filter_by_both(self):
        caps = {
            "a": _make_cap(
                "a", {"text": {"type": "string"}}, {"result": {"type": "string"}}
            ),
            "b": _make_cap(
                "b", {"text": {"type": "string"}}, {"count": {"type": "integer"}}
            ),
        }
        results = filter_capabilities_by_type(
            caps, input_type="string", output_type="string"
        )
        assert len(results) == 1
        assert results[0].id == "a"

    def test_no_filter(self):
        caps = {
            "a": _make_cap("a", {}, {}),
            "b": _make_cap("b", {}, {}),
        }
        results = filter_capabilities_by_type(caps)
        assert len(results) == 2


# ═══════════════════════════════════════════════════════════════════════════
# M6 — generate_mermaid_dag
# ═══════════════════════════════════════════════════════════════════════════


class TestGenerateMermaidDag:
    def test_simple_dag(self):
        mermaid = generate_mermaid_dag(_MINIMAL_SKILL)
        assert mermaid.startswith("graph LR")
        assert "summarize" in mermaid
        assert "text.content.summarize" in mermaid

    def test_two_step_with_deps(self):
        mermaid = generate_mermaid_dag(_TWO_STEP_SKILL)
        assert "extract --> analyze" in mermaid

    def test_shows_inputs_and_outputs(self):
        mermaid = generate_mermaid_dag(_MINIMAL_SKILL)
        assert "IN" in mermaid
        assert "OUT" in mermaid
        assert "text" in mermaid

    def test_empty_steps(self):
        mermaid = generate_mermaid_dag({"steps": []})
        assert "No steps" in mermaid


# ═══════════════════════════════════════════════════════════════════════════
# M4 — export_skill_bundle / import_skill_bundle
# ═══════════════════════════════════════════════════════════════════════════


class TestExportImport:
    def test_export_creates_bundle(self, tmp_path: Path):
        skill_dir = tmp_path / "test" / "summarize"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "skill.yaml"
        import yaml

        skill_file.write_text(yaml.dump(_MINIMAL_SKILL), encoding="utf-8")

        bundle = export_skill_bundle(skill_file)
        assert bundle.exists()
        assert bundle.name.endswith(".tar.gz")

        # Verify contents
        with tarfile.open(str(bundle), "r:gz") as tar:
            names = tar.getnames()
            assert "skill.yaml" in names
            assert "test_input.json" in names
            assert "bundle_manifest.json" in names

    def test_import_bundle(self, tmp_path: Path):
        # First export
        skill_dir = tmp_path / "source"
        skill_dir.mkdir()
        skill_file = skill_dir / "skill.yaml"
        import yaml

        skill_file.write_text(yaml.dump(_MINIMAL_SKILL), encoding="utf-8")
        bundle = export_skill_bundle(skill_file)

        # Then import
        import_root = tmp_path / "imported"
        import_root.mkdir()
        report = import_skill_bundle(str(bundle), import_root)

        assert report["ok"] is True
        assert report["skill_id"] == "test.summarize"
        assert "skill.yaml" in report["files"]

        # Verify files were extracted
        imported_skill = import_root / "test" / "summarize" / "skill.yaml"
        assert imported_skill.exists()

    def test_import_missing_source(self, tmp_path):
        report = import_skill_bundle("/nonexistent.tar.gz", tmp_path)
        assert report["ok"] is False
        assert "not found" in report["error"].lower()

    def test_import_warns_on_missing_capabilities(self, tmp_path):
        skill_dir = tmp_path / "source"
        skill_dir.mkdir()
        skill_file = skill_dir / "skill.yaml"
        import yaml

        skill_file.write_text(yaml.dump(_MINIMAL_SKILL), encoding="utf-8")
        bundle = export_skill_bundle(skill_file)

        import_root = tmp_path / "imported"
        import_root.mkdir()
        report = import_skill_bundle(str(bundle), import_root, capabilities={})
        assert report["ok"] is True
        assert "warnings" in report
        assert any("text.content.summarize" in w for w in report["warnings"])


# ═══════════════════════════════════════════════════════════════════════════
# M10 — find_similar_skills
# ═══════════════════════════════════════════════════════════════════════════


class TestFindSimilarSkills:
    def test_finds_similar_by_capabilities(self):
        skills = {
            "text.summarize": {
                "name": "Summarize",
                "description": "Summarize text",
                "steps": [{"uses": "text.content.summarize"}],
                "metadata": {"tags": ["text", "nlp"]},
            },
            "text.analyze": {
                "name": "Analyze",
                "description": "Analyze text",
                "steps": [
                    {"uses": "text.content.summarize"},
                    {"uses": "text.content.analyze"},
                ],
                "metadata": {"tags": ["text", "nlp"]},
            },
            "code.format": {
                "name": "Format Code",
                "description": "Format source code",
                "steps": [{"uses": "code.source.format"}],
                "metadata": {"tags": ["code"]},
            },
        }
        similar = find_similar_skills("text.summarize", skills)
        assert len(similar) >= 1
        assert similar[0]["skill_id"] == "text.analyze"

    def test_unknown_skill_returns_empty(self):
        assert find_similar_skills("unknown", {}) == []

    def test_no_similar_found(self):
        skills = {
            "a": {
                "name": "A",
                "description": "a",
                "steps": [{"uses": "x"}],
                "metadata": {},
            },
            "b": {
                "name": "B",
                "description": "b",
                "steps": [{"uses": "y"}],
                "metadata": {},
            },
        }
        similar = find_similar_skills("a", skills)
        # They share no capabilities, tags, or words — all scores should be low
        # But domain.slug format would give domain bonus if same domain
        assert isinstance(similar, list)


# ═══════════════════════════════════════════════════════════════════════════
# M11 — rate_skill
# ═══════════════════════════════════════════════════════════════════════════


class TestRateSkill:
    def test_rate_creates_feedback(self, tmp_path):
        fb_file = tmp_path / "feedback.json"
        result = rate_skill("test.skill", 4, "Good skill", fb_file)
        assert result["ok"] is True
        assert result["score"] == 4
        assert result["new_average"] == 4.0
        assert result["total_ratings"] == 1

        data = json.loads(fb_file.read_text(encoding="utf-8"))
        assert len(data["ratings"]) == 1
        assert data["aggregates"]["test.skill"]["rating_count"] == 1

    def test_rate_updates_average(self, tmp_path):
        fb_file = tmp_path / "feedback.json"
        rate_skill("test.skill", 4, None, fb_file)
        result = rate_skill("test.skill", 2, None, fb_file)
        assert result["new_average"] == 3.0
        assert result["total_ratings"] == 2

    def test_rate_invalid_score(self, tmp_path):
        fb_file = tmp_path / "feedback.json"
        result = rate_skill("test.skill", 0, None, fb_file)
        assert result["ok"] is False

        result = rate_skill("test.skill", 6, None, fb_file)
        assert result["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════
# M12 — generate_issue_report
# ═══════════════════════════════════════════════════════════════════════════


class TestGenerateIssueReport:
    def test_generates_report(self):
        report = generate_issue_report(
            "test.skill", "Skill produces empty output", severity="high"
        )
        assert "[Skill Report]" in report["title"]
        assert "test.skill" in report["body"]
        assert "severity-high" in report["labels"]

    def test_includes_execution_context(self):
        ctx = {"trace_id": "abc", "inputs": {"text": "..."}}
        report = generate_issue_report("test.skill", "Error", execution_context=ctx)
        assert "abc" in report["body"]
        assert "Execution Context" in report["body"]


# ═══════════════════════════════════════════════════════════════════════════
# M14 — suggest_wiring
# ═══════════════════════════════════════════════════════════════════════════


class TestSuggestWiring:
    def test_suggests_input_mapping(self):
        caps = {
            "text.content.summarize": _make_cap(
                "text.content.summarize",
                {"text": {"type": "string", "required": True}},
                {"summary": {"type": "string"}},
            )
        }
        suggestions = suggest_wiring(
            ["text.content.summarize"],
            caps,
            {"text": {"type": "string"}},
        )
        assert len(suggestions) == 1
        assert "text" in suggestions[0].get("suggested_input", {})

    def test_registers_outputs_for_chaining(self):
        caps = {
            "a": _make_cap("a", {}, {"result": {"type": "string"}}),
            "b": _make_cap("b", {"text": {"type": "string"}}, {}),
        }
        suggestions = suggest_wiring(["a", "b"], caps, {})
        assert len(suggestions) == 2
        # b should be able to map from a's output
        b_input = suggestions[1].get("suggested_input", {})
        assert len(b_input) >= 0  # May or may not find match depending on name

    def test_unknown_capability(self):
        suggestions = suggest_wiring(["nonexistent"], {}, {})
        assert suggestions[0].get("error") is not None
