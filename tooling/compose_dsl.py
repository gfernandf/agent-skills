"""Compose DSL — define multi-step skill workflows in a compact text syntax.

The compose DSL lets users define pipelines without writing full YAML, then
compiles them into standard skill.yaml documents.

Syntax (one step per line)::

    # Comments start with #
    @id my.composed-skill
    @name My Composed Skill
    @description A short description

    step1 = text.content.summarize(text=$input.text, max_length=100)
    step2 = text.content.translate(text=$step1.summary, target_language="es")

    > translated_summary = $step2.translated_text
    > original_summary = $step1.summary

Syntax rules:

- ``@id``, ``@name``, ``@description``: metadata directives
- ``step_id = capability(param=value, ...)`` : step definition
- ``$input.field`` : reference to skill input
- ``$step_id.field`` : reference to another step's output
- ``"literal"`` or ``123`` or ``true/false`` : literal values
- ``> output_name = $step.field`` : output mapping
- Lines starting with ``#`` are comments
- Empty lines are ignored

Example .compose file::

    @id text.translate-and-summarize
    @name Translate and Summarize
    @description Translate text then produce a summary

    summarize = text.content.summarize(text=$input.text, max_length=200)
    translate = text.content.translate(text=$summarize.summary, target_language=$input.lang)

    > result = $translate.translated_text

Usage::

    agent-skills compose my_pipeline.compose                     # Compile to YAML
    agent-skills compose my_pipeline.compose --run --input '{}'  # Compile + execute
    agent-skills compose my_pipeline.compose --out skill.yaml    # Write to file
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class ComposeStep:
    id: str
    capability: str
    params: dict[str, str]  # raw param expressions (before resolution)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class ComposeOutput:
    name: str
    expression: str  # e.g. "$step2.translated_text"


@dataclass
class ComposeSpec:
    skill_id: str
    name: str
    description: str
    steps: list[ComposeStep]
    outputs: list[ComposeOutput]
    raw_lines: list[str] = field(default_factory=list)


class ComposeParseError(Exception):
    def __init__(self, message: str, line_num: int = 0, line_text: str = ""):
        self.line_num = line_num
        self.line_text = line_text
        super().__init__(f"Line {line_num}: {message}")


# ── Regex patterns ──────────────────────────────────────────────────────

_RE_DIRECTIVE = re.compile(r"^@(\w+)\s+(.+)$")
_RE_STEP = re.compile(r"^(\w+)\s*=\s*([a-zA-Z0-9_.]+)\s*\((.+)\)\s*$")
_RE_OUTPUT = re.compile(r"^>\s*(\w+)\s*=\s*(.+)$")
_RE_PARAM = re.compile(r"(\w+)\s*=\s*(.+)")
_RE_REF = re.compile(r"^\$(\w+)\.(\w+)$")
_RE_STRING = re.compile(r'^"([^"]*)"$')
_RE_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def parse_compose(source: str, *, source_path: str = "<string>") -> ComposeSpec:
    """Parse a .compose source string into a ComposeSpec."""
    lines = source.strip().splitlines()

    skill_id = ""
    name = ""
    description = ""
    steps: list[ComposeStep] = []
    outputs: list[ComposeOutput] = []
    step_ids: set[str] = set()
    raw_lines: list[str] = []

    for line_num, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        raw_lines.append(raw_line)

        # Skip empty lines and comments
        if not line or line.startswith("#"):
            continue

        # Directives: @id, @name, @description
        m = _RE_DIRECTIVE.match(line)
        if m:
            key, value = m.group(1).lower(), m.group(2).strip()
            if key == "id":
                skill_id = value
            elif key == "name":
                name = value
            elif key == "description":
                description = value
            else:
                raise ComposeParseError(
                    f"Unknown directive '@{key}'", line_num, raw_line
                )
            continue

        # Output mapping: > output_name = $step.field
        m = _RE_OUTPUT.match(line)
        if m:
            out_name = m.group(1)
            out_expr = m.group(2).strip()
            outputs.append(ComposeOutput(name=out_name, expression=out_expr))
            continue

        # Step definition: step_id = capability(param=value, ...)
        m = _RE_STEP.match(line)
        if m:
            step_id = m.group(1)
            capability = m.group(2)
            params_str = m.group(3)

            if step_id in step_ids:
                raise ComposeParseError(
                    f"Duplicate step id '{step_id}'", line_num, raw_line
                )
            step_ids.add(step_id)

            params = _parse_params(params_str, line_num, raw_line)
            deps = _extract_deps(params, step_ids)

            steps.append(
                ComposeStep(
                    id=step_id,
                    capability=capability,
                    params=params,
                    depends_on=deps,
                )
            )
            continue

        raise ComposeParseError(f"Unrecognized syntax: {line}", line_num, raw_line)

    if not skill_id:
        raise ComposeParseError("Missing @id directive", 0, "")
    if not steps:
        raise ComposeParseError("No steps defined", 0, "")

    return ComposeSpec(
        skill_id=skill_id,
        name=name or skill_id,
        description=description or f"Composed skill: {skill_id}",
        steps=steps,
        outputs=outputs,
        raw_lines=raw_lines,
    )


def _parse_params(params_str: str, line_num: int, raw_line: str) -> dict[str, str]:
    """Parse a comma-separated param=value string."""
    params: dict[str, str] = {}
    # Split on commas, but respect quoted strings
    parts = _split_params(params_str)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = _RE_PARAM.match(part)
        if not m:
            raise ComposeParseError(f"Invalid parameter: {part}", line_num, raw_line)
        params[m.group(1)] = m.group(2).strip()
    return params


def _split_params(s: str) -> list[str]:
    """Split on commas, respecting quoted strings."""
    parts = []
    current = ""
    in_quotes = False
    for ch in s:
        if ch == '"':
            in_quotes = not in_quotes
            current += ch
        elif ch == "," and not in_quotes:
            parts.append(current)
            current = ""
        else:
            current += ch
    if current:
        parts.append(current)
    return parts


def _extract_deps(params: dict[str, str], known_steps: set[str]) -> list[str]:
    """Extract step dependencies from parameter references."""
    deps: list[str] = []
    for value in params.values():
        m = _RE_REF.match(value)
        if m and m.group(1) != "input" and m.group(1) in known_steps:
            if m.group(1) not in deps:
                deps.append(m.group(1))
    return deps


def _resolve_param_value(expr: str) -> dict[str, Any]:
    """Convert a param expression to a skill YAML input_mapping entry."""
    # Reference: $input.field or $step.field
    m = _RE_REF.match(expr)
    if m:
        source, field_name = m.group(1), m.group(2)
        if source == "input":
            return {"from_input": field_name}
        else:
            return {"from_step": source, "field": field_name}

    # String literal: "value"
    m = _RE_STRING.match(expr)
    if m:
        return {"value": m.group(1)}

    # Number literal
    m = _RE_NUMBER.match(expr)
    if m:
        return {"value": float(expr) if "." in expr else int(expr)}

    # Boolean
    if expr.lower() == "true":
        return {"value": True}
    if expr.lower() == "false":
        return {"value": False}

    # Treat as string literal
    return {"value": expr}


def compile_to_yaml(spec: ComposeSpec) -> dict[str, Any]:
    """Compile a ComposeSpec into a standard skill.yaml document."""
    # Detect which $input.X references are used
    input_fields: dict[str, str] = {}  # field_name → type (all string for now)
    for step in spec.steps:
        for value in step.params.values():
            m = _RE_REF.match(value)
            if m and m.group(1) == "input":
                input_fields[m.group(2)] = "string"

    # Build inputs section
    inputs: dict[str, Any] = {}
    for field_name, ftype in sorted(input_fields.items()):
        inputs[field_name] = {"type": ftype, "required": True}

    # Build steps
    steps_yaml: list[dict[str, Any]] = []
    for step in spec.steps:
        step_entry: dict[str, Any] = {
            "id": step.id,
            "uses": step.capability,
            "input_mapping": {},
        }
        for param, expr in step.params.items():
            resolved = _resolve_param_value(expr)
            step_entry["input_mapping"][param] = resolved

        if step.depends_on:
            step_entry["depends_on"] = step.depends_on

        steps_yaml.append(step_entry)

    # Build outputs section
    outputs_yaml: dict[str, Any] = {}
    for out in spec.outputs:
        m = _RE_REF.match(out.expression)
        if m:
            source, field_name = m.group(1), m.group(2)
            if source == "input":
                outputs_yaml[out.name] = {"from_input": field_name, "type": "string"}
            else:
                outputs_yaml[out.name] = {
                    "from_step": source,
                    "field": field_name,
                    "type": "string",
                }
        else:
            outputs_yaml[out.name] = {"value": out.expression, "type": "string"}

    skill_doc = {
        "id": spec.skill_id,
        "version": "1.0.0",
        "name": spec.name,
        "description": spec.description,
        "inputs": inputs,
        "outputs": outputs_yaml,
        "steps": steps_yaml,
    }
    return skill_doc


def compile_to_yaml_string(spec: ComposeSpec) -> str:
    """Compile a ComposeSpec to a YAML string."""
    doc = compile_to_yaml(spec)
    return yaml.dump(doc, default_flow_style=False, sort_keys=False, allow_unicode=True)


def parse_and_compile(source: str, *, source_path: str = "<string>") -> str:
    """One-shot: parse compose source and return compiled YAML string."""
    spec = parse_compose(source, source_path=source_path)
    return compile_to_yaml_string(spec)
