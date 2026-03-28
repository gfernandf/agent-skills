"""Tests for the shared JSON Schema helpers in sdk.embedded.

Validates _build_json_schema and _build_gemini_schema against all FieldSpec
types and edge cases that matter for MCP, Anthropic, OpenAI, and Gemini.
"""

from __future__ import annotations


from sdk.embedded import _build_json_schema, _build_gemini_schema


# ────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────

_CAP_STRING_REQUIRED = {
    "id": "test.cap",
    "description": "A test capability.",
    "inputs": {
        "text": {"type": "string", "required": True, "description": "The input text."},
    },
    "outputs": {},
}

_CAP_ALL_TYPES = {
    "id": "test.all_types",
    "description": "Capability with every supported type.",
    "inputs": {
        "name": {"type": "string", "required": True, "description": "A name."},
        "count": {"type": "integer", "required": False, "description": "How many."},
        "score": {"type": "number", "required": False, "description": "A score."},
        "active": {"type": "boolean", "required": True, "description": "Is it active?"},
        "tags": {"type": "array", "required": False, "description": "Tag list."},
        "metadata": {"type": "object", "required": False, "description": "Extra data."},
    },
    "outputs": {},
}

_CAP_NO_INPUTS = {
    "id": "test.empty",
    "description": "Capability with no inputs.",
    "inputs": {},
    "outputs": {},
}

_CAP_NO_DESCRIPTION = {
    "id": "test.nodesc",
    "description": "No field descriptions.",
    "inputs": {
        "value": {"type": "string", "required": True},
    },
    "outputs": {},
}

_CAP_ALL_OPTIONAL = {
    "id": "test.optional",
    "description": "All optional inputs.",
    "inputs": {
        "hint": {"type": "string", "required": False, "description": "A hint."},
        "limit": {"type": "integer", "required": False, "description": "Limit."},
    },
    "outputs": {},
}


# ────────────────────────────────────────────────────────────────
# _build_json_schema tests
# ────────────────────────────────────────────────────────────────


class TestBuildJsonSchema:
    """Tests for _build_json_schema — used by MCP, Anthropic, OpenAI."""

    def test_basic_string_required(self):
        schema = _build_json_schema(_CAP_STRING_REQUIRED)
        assert schema["type"] == "object"
        assert "text" in schema["properties"]
        assert schema["properties"]["text"]["type"] == "string"
        assert schema["properties"]["text"]["description"] == "The input text."
        assert schema["required"] == ["text"]

    def test_all_types_present(self):
        schema = _build_json_schema(_CAP_ALL_TYPES)
        props = schema["properties"]
        assert props["name"]["type"] == "string"
        assert props["count"]["type"] == "integer"
        assert props["score"]["type"] == "number"
        assert props["active"]["type"] == "boolean"
        assert props["tags"]["type"] == "array"
        assert props["metadata"]["type"] == "object"

    def test_required_fields_sorted(self):
        schema = _build_json_schema(_CAP_ALL_TYPES)
        assert schema["required"] == ["active", "name"]

    def test_array_has_items(self):
        """Arrays must include 'items' for strict-mode consumers (OpenAI)."""
        schema = _build_json_schema(_CAP_ALL_TYPES)
        assert "items" in schema["properties"]["tags"]
        assert schema["properties"]["tags"]["items"] == {}

    def test_object_type_valid(self):
        """Objects without sub-properties are valid JSON Schema."""
        schema = _build_json_schema(_CAP_ALL_TYPES)
        assert schema["properties"]["metadata"]["type"] == "object"
        # No sub-properties is valid — JSON Schema allows open objects
        assert "properties" not in schema["properties"]["metadata"]

    def test_no_inputs_returns_empty_schema(self):
        schema = _build_json_schema(_CAP_NO_INPUTS)
        assert schema["type"] == "object"
        assert schema["properties"] == {}
        assert "required" not in schema

    def test_no_description_omitted(self):
        """Fields without description should not have empty description key."""
        schema = _build_json_schema(_CAP_NO_DESCRIPTION)
        assert "description" not in schema["properties"]["value"]

    def test_all_optional_no_required_key(self):
        schema = _build_json_schema(_CAP_ALL_OPTIONAL)
        assert "required" not in schema

    def test_unknown_type_defaults_to_string(self):
        cap = {
            "inputs": {"custom": {"type": "foobar", "required": True}},
        }
        schema = _build_json_schema(cap)
        assert schema["properties"]["custom"]["type"] == "string"

    def test_missing_type_defaults_to_string(self):
        cap = {
            "inputs": {"nofield": {"required": False}},
        }
        schema = _build_json_schema(cap)
        assert schema["properties"]["nofield"]["type"] == "string"

    def test_schema_is_pure_dict(self):
        """Schema must be JSON-serializable (no custom types)."""
        import json

        schema = _build_json_schema(_CAP_ALL_TYPES)
        serialized = json.dumps(schema)
        assert isinstance(serialized, str)


# ────────────────────────────────────────────────────────────────
# _build_gemini_schema tests
# ────────────────────────────────────────────────────────────────


class TestBuildGeminiSchema:
    """Tests for _build_gemini_schema — Gemini uses UPPERCASE types."""

    def test_types_are_uppercase(self):
        schema = _build_gemini_schema(_CAP_ALL_TYPES)
        props = schema["properties"]
        assert props["name"]["type"] == "STRING"
        assert props["count"]["type"] == "INTEGER"
        assert props["score"]["type"] == "NUMBER"
        assert props["active"]["type"] == "BOOLEAN"
        assert props["tags"]["type"] == "ARRAY"
        assert props["metadata"]["type"] == "OBJECT"

    def test_root_type_is_uppercase_object(self):
        schema = _build_gemini_schema(_CAP_STRING_REQUIRED)
        assert schema["type"] == "OBJECT"

    def test_required_fields_sorted(self):
        schema = _build_gemini_schema(_CAP_ALL_TYPES)
        assert schema["required"] == ["active", "name"]

    def test_array_has_items_with_type(self):
        """Gemini arrays must have items with a type."""
        schema = _build_gemini_schema(_CAP_ALL_TYPES)
        assert schema["properties"]["tags"]["items"] == {"type": "STRING"}

    def test_no_inputs_returns_empty_schema(self):
        schema = _build_gemini_schema(_CAP_NO_INPUTS)
        assert schema["type"] == "OBJECT"
        assert schema["properties"] == {}

    def test_description_preserved(self):
        schema = _build_gemini_schema(_CAP_STRING_REQUIRED)
        assert schema["properties"]["text"]["description"] == "The input text."

    def test_unknown_type_defaults_to_string(self):
        cap = {"inputs": {"custom": {"type": "foobar", "required": True}}}
        schema = _build_gemini_schema(cap)
        assert schema["properties"]["custom"]["type"] == "STRING"

    def test_schema_is_pure_dict(self):
        import json

        schema = _build_gemini_schema(_CAP_ALL_TYPES)
        serialized = json.dumps(schema)
        assert isinstance(serialized, str)
