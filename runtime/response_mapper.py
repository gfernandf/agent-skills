from __future__ import annotations

import json
import re
from typing import Any

from runtime.binding_models import BindingSpec, InvocationResponse
from runtime.errors import RuntimeErrorBase


class ResponseMappingError(RuntimeErrorBase):
    """Raised when a binding response cannot be mapped into capability outputs."""


class ResponseMapper:
    """
    Map a protocol-agnostic invocation response into capability outputs.

    Binding response mappings operate on the invocation response using the namespace:

        response.<field-path>

    Example:
        response:
          summary: response.data.summary
          metadata: response.metadata

    Rules in v1:
    - every declared output mapping must resolve successfully
    - only the 'response.' namespace is interpreted as a response reference
    - non-reference strings are treated as literals
        - each output maps to either one string reference or a fallback list of
            references tried in order
    """

    def map(
        self,
        binding: BindingSpec,
        invocation_response: InvocationResponse,
        *,
        step_input: dict[str, Any] | None = None,
        request_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raw_response = invocation_response.raw_response

        if not isinstance(binding.response_mapping, dict):
            raise ResponseMappingError(
                f"Binding '{binding.id}' has an invalid response mapping.",
                capability_id=binding.capability_id,
            )

        mapped: dict[str, Any] = {}
        metadata = binding.metadata or {}
        allow_partial = bool(
            binding.protocol == "openapi"
            or metadata.get("status") == "experimental"
            or metadata.get("allow_partial_response_mapping") is True
        )
        last_error: ResponseMappingError | None = None

        for output_name, response_ref in binding.response_mapping.items():
            if not isinstance(output_name, str) or not output_name:
                raise ResponseMappingError(
                    f"Binding '{binding.id}' contains an invalid output name in response mapping.",
                    capability_id=binding.capability_id,
                )

            if isinstance(response_ref, str):
                if not response_ref:
                    raise ResponseMappingError(
                        f"Binding '{binding.id}' response mapping for '{output_name}' must be a non-empty string.",
                        capability_id=binding.capability_id,
                    )
                try:
                    mapped[output_name] = self._resolve_response_reference(
                        response_ref,
                        raw_response=raw_response,
                        binding=binding,
                        step_input=step_input,
                        request_payload=request_payload,
                    )
                except ResponseMappingError as exc:
                    if not allow_partial:
                        raise
                    fallback_value = self._synthesize_missing_output(
                        output_name=output_name,
                        mapped=mapped,
                        raw_response=raw_response,
                        step_input=step_input,
                    )
                    if fallback_value is not None:
                        mapped[output_name] = fallback_value
                    else:
                        last_error = exc
                continue

            if isinstance(response_ref, list):
                if not response_ref:
                    raise ResponseMappingError(
                        f"Binding '{binding.id}' response mapping list for '{output_name}' must not be empty.",
                        capability_id=binding.capability_id,
                    )
                try:
                    mapped[output_name] = self._resolve_with_fallbacks(
                        response_refs=response_ref,
                        raw_response=raw_response,
                        binding=binding,
                        step_input=step_input,
                        request_payload=request_payload,
                    )
                except ResponseMappingError as exc:
                    if not allow_partial:
                        raise
                    fallback_value = self._synthesize_missing_output(
                        output_name=output_name,
                        mapped=mapped,
                        raw_response=raw_response,
                        step_input=step_input,
                    )
                    if fallback_value is not None:
                        mapped[output_name] = fallback_value
                    else:
                        last_error = exc
                continue

            raise ResponseMappingError(
                f"Binding '{binding.id}' response mapping for '{output_name}' must be a string or a list of strings.",
                capability_id=binding.capability_id,
            )

        if allow_partial:
            for output_name in binding.response_mapping.keys():
                if output_name in mapped:
                    continue
                fallback_value = self._synthesize_missing_output(
                    output_name=output_name,
                    mapped=mapped,
                    raw_response=raw_response,
                    step_input=step_input,
                )
                if fallback_value is not None:
                    mapped[output_name] = fallback_value

            # In partial-mode bindings, providers often return contract-adjacent
            # shapes (e.g., object instead of summary string). Normalize these
            # values conservatively to keep outputs contract-compatible.
            for output_name, value in list(mapped.items()):
                mapped[output_name] = self._coerce_partial_output_value(
                    output_name=output_name,
                    value=value,
                    raw_response=raw_response,
                )

        if not mapped and last_error is not None:
            raise last_error

        return mapped

    def _coerce_partial_output_value(
        self,
        *,
        output_name: str,
        value: Any,
        raw_response: Any,
    ) -> Any:
        key = output_name.strip().lower()

        if key in {"state_checksum", "trace_version", "trace_session_id"}:
            text = self._as_text(value)
            return text if text is not None else value

        if key == "trace_summary":
            obj = self._as_object(value)
            return obj if obj is not None else value

        if key == "context":
            obj = self._as_object(value)
            if obj is not None:
                return obj
            context_id = (step_input or {}).get("context_id")
            context_obj: dict[str, Any] = {}
            if isinstance(context_id, str) and context_id.strip():
                context_obj["context_id"] = context_id.strip()
            text = self._as_text(value)
            if text is not None:
                context_obj["value"] = text
            elif value is not None:
                context_obj["value"] = value
            if not context_obj:
                return {"status": "unknown"}
            return context_obj

        if key in {"confidence_summary", "prioritization_summary", "selection_rationale"}:
            text = self._as_text(value)
            return text if text is not None else value

        if key in {"evaluation", "authorization_result"}:
            obj = self._as_object(value)
            return obj if obj is not None else value

        if key == "tradeoffs":
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                return [value]
            if isinstance(value, str) and value.strip():
                return [{"summary": value.strip()}]
            return []

        if key in {"success_criteria", "quality_criteria", "acceptance_criteria"}:
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                normalized: list[str] = []
                for raw in value.values():
                    text = self._as_text(raw)
                    if text:
                        normalized.append(text)
                return normalized
            if isinstance(value, str) and value.strip():
                return [value.strip()]
            return []

        if key == "differences":
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                normalized: list[dict[str, Any]] = []
                for dim, raw in value.items():
                    if isinstance(raw, dict):
                        row = dict(raw)
                        row.setdefault("dimension", str(dim))
                        normalized.append(row)
                    elif raw is not None:
                        normalized.append({"dimension": str(dim), "summary": self._as_text(raw) or str(raw)})
                return normalized
            if isinstance(value, str) and value.strip():
                return [{"summary": value.strip()}]
            return []

        if key == "removals":
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                return [value]
            if isinstance(value, str):
                lowered = value.strip().lower()
                if not lowered or lowered in {"success", "ok", "none", "clean"}:
                    return []
                return [{"summary": value.strip()}]
            return []

        if key == "expanded_steps":
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                for candidate_key in ("steps", "expanded_steps", "plan", "items"):
                    candidate_value = value.get(candidate_key)
                    if isinstance(candidate_value, list):
                        return candidate_value
                return [value] if value else []
            if isinstance(value, str) and value.strip():
                return [{"description": value.strip()}]
            return []

        if key == "components":
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                for candidate_key in ("components", "items", "subproblems", "steps"):
                    candidate_value = value.get(candidate_key)
                    if isinstance(candidate_value, list):
                        return candidate_value
                return [value] if value else []
            if isinstance(value, str) and value.strip():
                return [{"description": value.strip()}]
            return []

        if key == "sanitized_output":
            if isinstance(value, dict):
                return value
            if isinstance(value, list):
                return {"items": value}
            if isinstance(value, str) and value.strip():
                return {"summary": value.strip()}
            return {"status": "available"}

        if key == "plan":
            if isinstance(value, dict):
                return value
            if isinstance(value, list):
                return {"steps": value, "status": "ready"}
            if isinstance(value, str) and value.strip():
                return {"summary": value.strip(), "status": "ready"}
            return {"steps": [], "status": "ready"}

        if key == "compiled_plan":
            if isinstance(value, dict):
                return value
            if isinstance(value, list):
                return {
                    "id": "reasoning-plan-synthesize",
                    "steps": value,
                    "status": "ready",
                }
            if isinstance(value, str) and value.strip():
                parsed = self._as_object(value)
                if parsed is not None:
                    return parsed
                return {
                    "id": "reasoning-plan-synthesize",
                    "steps": [{"id": "step-1", "description": value.strip()}],
                    "status": "ready",
                }
            return {"id": "reasoning-plan-synthesize", "steps": [], "status": "ready"}

        if key in {"selection_confidence", "recurrence_risk"} or key.endswith("_confidence"):
            number = self._as_number(value)
            return number if number is not None else value

        if key == "report_status":
            text = self._as_text(value)
            if text is None:
                return "success"
            lowered = text.strip().lower()
            if lowered in {"ok", "done", "complete", "completed", "ready", "pass", "passed"}:
                return "success"
            if lowered in {"fail", "failed", "error", "blocked"}:
                return "failed"
            return lowered

        if key == "confidence":
            number = self._as_number(value)
            if number is None:
                return 0.5
            return max(0.0, min(1.0, number))

        if key == "clean":
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            if isinstance(value, list):
                return len(value) == 0
            if isinstance(value, dict):
                return len(value) == 0
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"true", "yes", "clean", "safe", "ok", "none", "pass", "passed", "success"}:
                    return True
                if lowered in {"false", "no", "unclean", "unsafe", "fail", "failed", "error"}:
                    return False
            return False

        if key == "step_count":
            number = self._as_number(value)
            if number is not None:
                return int(number)
            if isinstance(value, list):
                return len(value)
            if isinstance(value, dict):
                for candidate_key in ("steps", "expanded_steps", "plan", "items"):
                    candidate_value = value.get(candidate_key)
                    if isinstance(candidate_value, list):
                        return len(candidate_value)
                return 0
            return 0

        if key in {"score", "overall", "risk_score"}:
            number = self._as_number(value)
            if number is None:
                return value
            return max(0.0, min(1.0, number))

        if key == "dimensions" and isinstance(value, dict):
            normalized: dict[str, Any] = {}
            for dim, raw in value.items():
                if isinstance(raw, dict):
                    score = self._as_number(raw.get("score"))
                    if score is not None:
                        row = dict(raw)
                        row["score"] = max(0.0, min(1.0, score))
                        normalized[str(dim)] = row
                    else:
                        normalized[str(dim)] = raw
                    continue
                score = self._as_number(raw)
                if score is not None:
                    normalized[str(dim)] = max(0.0, min(1.0, score))
                else:
                    normalized[str(dim)] = raw
            return normalized

        if key == "selected_strategy" and isinstance(value, str):
            txt = value.strip()
            if txt:
                return {"id": txt}

        if key == "root_causes":
            coerced = self._coerce_root_causes(value)
            if coerced is not None:
                return coerced

        if key == "failure_class":
            if isinstance(value, dict):
                candidate = self._first_text(
                    value.get("failure_class"),
                    value.get("class"),
                    value.get("type"),
                    value.get("value"),
                )
                if candidate:
                    return candidate

        # last chance for known summary-like outputs: infer text from response
        if key.endswith("_summary") and not isinstance(value, str):
            text = self._first_text(
                self._as_text(value),
                self._as_text(self._find_first_scalar_by_keys(raw_response, ["summary", "rationale", "content", "message"])),
            )
            if text:
                return text

        return value

    def _coerce_root_causes(self, value: Any) -> list[dict[str, Any]] | None:
        if isinstance(value, list):
            normalized: list[dict[str, Any]] = []
            for i, item in enumerate(value, start=1):
                if isinstance(item, dict):
                    normalized.append(item)
                elif isinstance(item, str) and item.strip():
                    normalized.append(
                        {
                            "id": f"rc-{i}",
                            "description": item.strip(),
                            "confidence": 0.5,
                        }
                    )
            return normalized if normalized else None

        if isinstance(value, dict):
            items = value.get("identified_causes")
            if isinstance(items, list):
                normalized: list[dict[str, Any]] = []
                for i, item in enumerate(items, start=1):
                    if isinstance(item, dict):
                        normalized.append(item)
                    elif isinstance(item, str) and item.strip():
                        normalized.append(
                            {
                                "id": f"rc-{i}",
                                "description": item.strip(),
                                "confidence": 0.5,
                            }
                        )
                if normalized:
                    return normalized

        if isinstance(value, str) and value.strip():
            return [{"id": "rc-1", "description": value.strip(), "confidence": 0.5}]

        return None

    def _as_text(self, value: Any) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, dict):
            direct = self._first_text(
                value.get("summary"),
                value.get("rationale"),
                value.get("explanation"),
                value.get("message"),
                value.get("content"),
            )
            if direct:
                return direct
            content_json = value.get("content_json")
            if isinstance(content_json, dict):
                nested = self._first_text(
                    content_json.get("summary"),
                    content_json.get("rationale"),
                    content_json.get("message"),
                )
                if nested:
                    return nested
            try:
                return json.dumps(value, ensure_ascii=False)
            except Exception:
                return None
        if isinstance(value, list):
            try:
                return json.dumps(value, ensure_ascii=False)
            except Exception:
                return None
        return None

    def _as_number(self, value: Any) -> float | None:
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, list):
            for item in value:
                parsed = self._as_number(item)
                if parsed is not None:
                    return parsed
            return None
        if isinstance(value, str):
            s = value.strip().lower()
            try:
                return float(s)
            except Exception:
                if s.endswith("%"):
                    try:
                        return float(s[:-1].strip()) / 100.0
                    except Exception:
                        pass

                match = re.search(r"-?\d+(?:\.\d+)?", s)
                if match is not None:
                    try:
                        parsed = float(match.group(0))
                        if 1.0 < parsed <= 100.0 and ("%" in s or "percent" in s):
                            return parsed / 100.0
                        return parsed
                    except Exception:
                        pass

                if s in {"low", "minor"}:
                    return 0.25
                if s in {"medium", "moderate"}:
                    return 0.55
                if s in {"high", "severe", "critical"}:
                    return 0.85
                return None
        if isinstance(value, dict):
            for key in ("score", "confidence", "value", "recurrence_risk"):
                raw = value.get(key)
                parsed = self._as_number(raw)
                if parsed is not None:
                    return parsed
            risk_level = value.get("risk_level")
            parsed_risk = self._as_number(risk_level)
            if parsed_risk is not None:
                return parsed_risk
        return None

    def _as_object(self, value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            txt = value.strip()
            if not txt:
                return None
            try:
                parsed = json.loads(txt)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {"summary": txt}
            return {"summary": txt}
        if isinstance(value, (int, float, bool)):
            return {"value": value}
        if isinstance(value, list):
            return {"items": value}
        return None

    def _synthesize_missing_output(
        self,
        *,
        output_name: str,
        mapped: dict[str, Any],
        raw_response: Any,
        step_input: dict[str, Any] | None = None,
    ) -> Any | None:
        key = output_name.strip().lower()
        if not key:
            return None

        narrative = self._first_text(
            mapped.get("rationale"),
            mapped.get("reasoning"),
            mapped.get("explanation"),
            self._find_first_scalar_by_keys(raw_response, ["rationale", "reasoning", "explanation", "summary"]),
        )

        if key.endswith("_rationale"):
            if narrative:
                return narrative
            if mapped.get("selected_option") is not None:
                return "Selection rationale inferred from selected option and available signals."
            return None

        if key == "rationale":
            if narrative:
                return narrative
            return self._first_text(self._as_text(raw_response), "Partial rationale inferred from OpenAPI response.")

        if key == "sentiment":
            inferred = self._find_first_scalar_by_keys(
                raw_response,
                ["sentiment", "polarity", "label", "tone", "classification"],
            )
            text = self._as_text(inferred)
            if isinstance(text, str) and text.strip():
                lowered = text.strip().lower()
                if lowered in {"positive", "negative", "neutral", "mixed"}:
                    return lowered
                if lowered in {"pos", "favorable", "favourable", "good"}:
                    return "positive"
                if lowered in {"neg", "unfavorable", "unfavourable", "bad"}:
                    return "negative"
                if lowered in {"balanced", "unclear", "unknown"}:
                    return "neutral"

            score_value = mapped.get("score")
            score = self._as_number(score_value)
            if score is None:
                score = self._as_number(
                    self._find_first_scalar_by_keys(raw_response, ["score", "polarity_score", "sentiment_score"])
                )
            if score is not None:
                if score >= 0.15:
                    return "positive"
                if score <= -0.15:
                    return "negative"
                return "neutral"
            return "neutral"

        if key == "sanitized_output":
            inferred = self._find_first_scalar_by_keys(
                raw_response,
                ["sanitized_output", "output", "normalized_output", "content", "text"],
            )
            if inferred is not None:
                return inferred
            source_output = (step_input or {}).get("output")
            if source_output is not None:
                return source_output
            return {}

        if key == "plan":
            inferred = self._find_first_scalar_by_keys(
                raw_response,
                ["plan", "steps", "execution_plan", "plan_steps", "expanded_steps"],
            )
            if inferred is not None:
                return inferred
            objective = (step_input or {}).get("objective")
            if isinstance(objective, str) and objective.strip():
                return {
                    "id": "reasoning-plan-generate",
                    "steps": [
                        {"id": "step-1", "action": "analyze", "description": objective.strip()},
                        {"id": "step-2", "action": "execute", "description": "Execute generated plan."},
                    ],
                    "status": "ready",
                }
            return {"id": "reasoning-plan-generate", "steps": [], "status": "ready"}

        if key == "clean":
            inferred = self._find_first_scalar_by_keys(raw_response, ["clean", "is_clean", "safe", "status"])
            if isinstance(inferred, bool):
                return inferred
            if isinstance(inferred, (int, float)):
                return bool(inferred)
            if isinstance(inferred, str):
                lowered = inferred.strip().lower()
                if lowered in {"true", "yes", "clean", "safe", "ok", "none", "pass", "passed", "success"}:
                    return True
                if lowered in {"false", "no", "unclean", "unsafe", "fail", "failed", "error"}:
                    return False
            removals_value = mapped.get("removals")
            if isinstance(removals_value, list):
                return len(removals_value) == 0
            if isinstance(removals_value, dict):
                return len(removals_value) == 0
            return False

        if key == "gap_severity":
            caps = self._find_first_scalar_by_keys(raw_response, ["missing_capabilities", "capability_gaps"])
            skills = self._find_first_scalar_by_keys(raw_response, ["missing_skills", "skill_gaps"])
            cap_count = len(caps) if isinstance(caps, list) else 0
            skill_count = len(skills) if isinstance(skills, list) else 0
            total = cap_count + skill_count
            if total == 0:
                return "none"
            if total >= 3:
                return "blocking"
            return "minor"

        if key == "label":
            inferred = self._find_first_scalar_by_keys(raw_response, ["label", "classification", "category"])
            text = self._as_text(inferred)
            if text:
                return text
            labels = (step_input or {}).get("labels")
            if isinstance(labels, list) and labels:
                first = labels[0]
                if isinstance(first, str) and first.strip():
                    return first.strip()
                if isinstance(first, dict):
                    candidate = self._first_text(first.get("label"), first.get("id"), first.get("name"))
                    if candidate:
                        return candidate
            return "unknown"

        if key == "item_count":
            items = (step_input or {}).get("items")
            if isinstance(items, list):
                return len(items)
            inferred = self._find_first_scalar_by_keys(raw_response, ["item_count", "count", "items_count"])
            parsed = self._as_number(inferred)
            if parsed is not None:
                return int(parsed)
            return 0

        if key == "conflict_severity":
            inferred = self._find_first_scalar_by_keys(
                raw_response,
                ["conflict_severity", "severity", "overall_severity", "risk_level"],
            )
            text = self._first_text(inferred)
            if text:
                lowered = text.strip().lower()
                if lowered in {"low", "minor", "none", "no_conflict"}:
                    return "low"
                if lowered in {"high", "severe", "critical", "blocking"}:
                    return "high"
                return "medium" if lowered == "moderate" else lowered

            conflicts = mapped.get("conflicts")
            if isinstance(conflicts, list):
                count = len(conflicts)
                if count == 0:
                    return "low"
                if count >= 3:
                    return "high"
                return "medium"

        if key == "ranked_hypotheses":
            ranked = self._find_first_scalar_by_keys(raw_response, ["ranked_hypotheses", "hypotheses_ranked", "ranked"])
            if isinstance(ranked, list) and ranked:
                return ranked
            evaluated = (step_input or {}).get("evaluated_hypotheses")
            if isinstance(evaluated, list) and evaluated:
                normalized = []
                for i, item in enumerate(evaluated, start=1):
                    if isinstance(item, dict):
                        normalized.append(
                            {
                                "hypothesis_id": item.get("hypothesis_id", item.get("id", f"h{i}")),
                                "rank": i,
                                "score": item.get("support_score", item.get("score", 0.5)),
                            }
                        )
                    else:
                        normalized.append({"hypothesis_id": f"h{i}", "rank": i, "score": 0.5})
                return normalized

        if key == "score":
            inferred = self._find_first_scalar_by_keys(raw_response, ["score", "overall", "overall_score", "quality_score"])
            parsed = self._as_number(inferred)
            if parsed is not None:
                return parsed
            dims = self._find_first_scalar_by_keys(raw_response, ["dimensions", "dimension_scores", "scores"])
            if isinstance(dims, dict):
                values: list[float] = []
                for item in dims.values():
                    n = self._as_number(item)
                    if n is not None:
                        values.append(n)
                    elif isinstance(item, dict):
                        n2 = self._as_number(item.get("score"))
                        if n2 is not None:
                            values.append(n2)
                if values:
                    return sum(values) / len(values)

        if key == "confidence":
            inferred = self._find_first_scalar_by_keys(
                raw_response,
                ["confidence", "confidence_score", "score", "likelihood"],
            )
            parsed = self._as_number(inferred)
            if parsed is not None:
                return max(0.0, min(1.0, parsed))
            label = mapped.get("label")
            if isinstance(label, str) and label.strip():
                return 0.5
            return 0.5

        if key == "label":
            text = self._as_text(value)
            return text if text is not None else value

        if key == "item_count":
            number = self._as_number(value)
            if number is not None:
                return int(number)
            return value

        if key == "differences":
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                return [value]
            inferred = self._find_first_scalar_by_keys(
                raw_response,
                ["differences", "difference_list", "delta", "deltas"],
            )
            if isinstance(inferred, list):
                return inferred
            if isinstance(inferred, dict):
                return [inferred]
            text = self._as_text(inferred)
            if text:
                return [{"summary": text}]
            summary = self._first_text(
                self._as_text(self._find_first_scalar_by_keys(raw_response, ["summary", "rationale", "message", "content"])),
            )
            if summary:
                return [{"summary": summary}]
            return []

        if key == "risk_score":
            inferred = self._find_first_scalar_by_keys(
                raw_response,
                ["risk_score", "overall_risk", "overall", "score", "risk_level"],
            )
            parsed = self._as_number(inferred)
            if parsed is not None:
                return max(0.0, min(1.0, parsed))

            dims = mapped.get("dimension_scores")
            if isinstance(dims, dict) and dims:
                values: list[float] = []
                for item in dims.values():
                    n = self._as_number(item)
                    if n is not None:
                        values.append(n)
                    elif isinstance(item, dict):
                        n2 = self._as_number(item.get("score"))
                        if n2 is not None:
                            values.append(n2)
                if values:
                    avg = sum(values) / len(values)
                    return max(0.0, min(1.0, avg))
            return 0.5

        if key == "assumptions":
            inferred = self._find_first_scalar_by_keys(
                raw_response,
                ["assumptions", "fragile_assumptions", "implicit_assumptions"],
            )
            if isinstance(inferred, list):
                return inferred
            if isinstance(inferred, dict):
                return [inferred]

            risks = mapped.get("risks")
            if isinstance(risks, list) and risks:
                synthesized: list[dict[str, Any]] = []
                for i, item in enumerate(risks[:3], start=1):
                    risk_id = None
                    if isinstance(item, dict):
                        candidate = item.get("id")
                        if isinstance(candidate, str) and candidate.strip():
                            risk_id = candidate.strip()
                    assumption_id = f"asm-{i}"
                    row: dict[str, Any] = {
                        "id": assumption_id,
                        "statement": "Critical dependency remains valid for execution.",
                        "fragility_hint": "medium",
                    }
                    if risk_id:
                        row["related_risks"] = [risk_id]
                    synthesized.append(row)
                return synthesized
            return []

        if key == "failure_modes":
            inferred = self._find_first_scalar_by_keys(
                raw_response,
                ["failure_modes", "failures", "failure_scenarios"],
            )
            if isinstance(inferred, list):
                return inferred
            if isinstance(inferred, dict):
                return [inferred]

            risks = mapped.get("risks")
            if isinstance(risks, list) and risks:
                synthesized_modes: list[dict[str, Any]] = []
                for i, item in enumerate(risks[:3], start=1):
                    risk_id = None
                    if isinstance(item, dict):
                        candidate = item.get("id")
                        if isinstance(candidate, str) and candidate.strip():
                            risk_id = candidate.strip()
                    mode: dict[str, Any] = {
                        "id": f"fm-{i}",
                        "description": "Execution deviates from expected conditions.",
                        "trigger_conditions": ["Insufficient evidence or coordination"],
                    }
                    if risk_id:
                        mode["related_risks"] = [risk_id]
                    synthesized_modes.append(mode)
                return synthesized_modes
            return []

        if key in {"missing_capabilities", "missing_skills"}:
            inferred = self._find_first_scalar_by_keys(raw_response, [key])
            if isinstance(inferred, list):
                return inferred
            return []

        if key == "conflicts":
            inferred = self._find_first_scalar_by_keys(
                raw_response,
                ["conflicts", "inconsistencies", "contradictions"],
            )
            if isinstance(inferred, list):
                return inferred
            if isinstance(inferred, dict):
                return [inferred]
            return []

        if key == "missing_fields":
            inferred = self._find_first_scalar_by_keys(
                raw_response,
                ["missing_fields", "missing", "absent_fields", "omitted_fields"],
            )
            if isinstance(inferred, list):
                return inferred
            if isinstance(inferred, dict):
                return [str(name) for name in inferred.keys()]

            fields = (step_input or {}).get("fields")
            if isinstance(fields, list):
                missing: list[str] = []
                for item in fields:
                    if isinstance(item, dict):
                        name = item.get("name")
                        if isinstance(name, str) and name.strip():
                            missing.append(name.strip())
                return missing
            return []

        if key == "structured_input":
            inferred = self._find_first_scalar_by_keys(
                raw_response,
                ["structured_input", "structured", "input_structure"],
            )
            if isinstance(inferred, dict) and inferred:
                return inferred

            fields = (step_input or {}).get("fields")
            raw_input = (step_input or {}).get("raw_input")
            if isinstance(fields, list) and isinstance(raw_input, dict):
                structured: dict[str, Any] = {}
                for item in fields:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name")
                    if not isinstance(name, str) or not name.strip():
                        continue
                    field_name = name.strip()
                    if field_name in raw_input:
                        structured[field_name] = raw_input[field_name]
                        continue

                    lower_name = field_name.lower()
                    candidates = [
                        lower_name,
                        f"{lower_name}_text",
                        f"{lower_name}_value",
                        f"{lower_name}s",
                        lower_name.replace("_", ""),
                    ]
                    found_value = None
                    for candidate in candidates:
                        if candidate in raw_input:
                            found_value = raw_input[candidate]
                            break
                    if found_value is None and lower_name == "objective":
                        found_value = raw_input.get("objective_text")
                    if found_value is None and lower_name == "constraints":
                        found_value = raw_input.get("hard_constraints")
                    structured[field_name] = found_value if found_value is not None else f"missing:{field_name}"
                return structured
            return {}

        if key == "complete":
            inferred = self._find_first_scalar_by_keys(raw_response, ["complete", "is_complete", "finished"])
            if isinstance(inferred, bool):
                return inferred
            if isinstance(inferred, (int, float)):
                return bool(inferred)
            if isinstance(inferred, str):
                lowered = inferred.strip().lower()
                if lowered in {"true", "yes", "complete", "completed", "done"}:
                    return True
                if lowered in {"false", "no", "incomplete", "partial"}:
                    return False

            missing = mapped.get("missing_fields")
            if isinstance(missing, list):
                return len(missing) == 0
            return True

        if key == "dimension_scores":
            inferred = self._find_first_scalar_by_keys(
                raw_response,
                ["dimension_scores", "scores", "dimensions"],
            )
            if isinstance(inferred, dict) and inferred:
                return inferred
            dims = (step_input or {}).get("dimensions")
            if isinstance(dims, list) and dims:
                return {str(d): 0.5 for d in dims if isinstance(d, (str, int, float))}
            return {}

        if key == "source_scores":
            inferred = self._find_first_scalar_by_keys(
                raw_response,
                ["source_scores", "scores", "source_ratings"],
            )
            if isinstance(inferred, list):
                return inferred
            if isinstance(inferred, dict):
                return [
                    {"source": str(name), "score": self._as_number(score) or 0.5}
                    for name, score in inferred.items()
                ]
            sources = (step_input or {}).get("sources")
            if isinstance(sources, list) and sources:
                synthesized: list[dict[str, Any]] = []
                for i, item in enumerate(sources, start=1):
                    if isinstance(item, dict):
                        synthesized.append(
                            {
                                "source": item.get("id", item.get("name", f"source-{i}")),
                                "score": 0.5,
                            }
                        )
                    else:
                        synthesized.append({"source": f"source-{i}", "score": 0.5})
                return synthesized
            return []

        if key == "verified":
            inferred = self._find_first_scalar_by_keys(raw_response, ["verified", "is_verified", "supported"])
            if isinstance(inferred, bool):
                return inferred
            if isinstance(inferred, (int, float)):
                return bool(inferred)
            if isinstance(inferred, str):
                return inferred.strip().lower() in {"true", "yes", "verified", "supported"}

            evidence = mapped.get("evidence")
            if isinstance(evidence, list):
                return len(evidence) > 0
            if isinstance(evidence, dict):
                return True

            status = self._first_text(mapped.get("status"), self._find_first_scalar_by_keys(raw_response, ["status"]))
            if status:
                lowered = status.strip().lower()
                if lowered in {"verified", "supported", "success", "ok", "passed", "true"}:
                    return True
                if lowered in {"failed", "false", "unverified", "unsupported", "error"}:
                    return False
            return False

        if key == "safe":
            inferred = self._find_first_scalar_by_keys(raw_response, ["safe", "is_safe"])
            if isinstance(inferred, bool):
                return inferred
            if isinstance(inferred, (int, float)):
                return bool(inferred)
            if isinstance(inferred, str):
                lowered = inferred.strip().lower()
                if lowered in {"true", "yes", "safe", "ok", "low"}:
                    return True
                if lowered in {"false", "no", "unsafe", "high", "critical"}:
                    return False

            risk_score = self._as_number(mapped.get("risk_score"))
            if risk_score is None:
                risk_score = self._as_number(
                    self._find_first_scalar_by_keys(raw_response, ["risk_score", "score", "overall"])
                )
            if risk_score is not None:
                return risk_score <= 0.4

            flags = mapped.get("flags")
            if isinstance(flags, list):
                return len(flags) == 0
            return True

        if key == "scores":
            inferred = self._find_first_scalar_by_keys(raw_response, ["scores", "dimension_scores", "metrics"])
            if isinstance(inferred, dict) and inferred:
                return inferred
            dims = (step_input or {}).get("dimensions")
            if isinstance(dims, list) and dims:
                return {
                    str(d): 0.5
                    for d in dims
                    if isinstance(d, (str, int, float))
                }

        if key == "overall":
            inferred = self._find_first_scalar_by_keys(raw_response, ["overall", "overall_score", "score"])
            parsed = self._as_number(inferred)
            if parsed is not None:
                return parsed
            scores = mapped.get("scores")
            if isinstance(scores, dict) and scores:
                vals = [self._as_number(v) for v in scores.values()]
                vals = [v for v in vals if v is not None]
                if vals:
                    return sum(vals) / len(vals)

        if key == "criteria_used":
            criteria = (step_input or {}).get("criteria")
            if isinstance(criteria, list) and criteria:
                return criteria
            inferred = self._find_first_scalar_by_keys(raw_response, ["criteria", "applied_criteria", "criteria_used"])
            if isinstance(inferred, list) and inferred:
                return inferred
            return []

        if key == "tradeoffs":
            inferred = self._find_first_scalar_by_keys(raw_response, ["tradeoffs", "trade_offs", "option_tradeoffs"])
            if isinstance(inferred, list):
                return inferred
            if isinstance(inferred, str) and inferred.strip():
                return [{"summary": inferred.strip()}]
            return []

        if key == "validated_assumptions":
            existing = self._find_first_scalar_by_keys(
                raw_response,
                ["validated_assumptions", "assumptions", "validation_results"],
            )
            if isinstance(existing, list) and existing:
                normalized: list[dict[str, Any]] = []
                for i, item in enumerate(existing, start=1):
                    if isinstance(item, dict):
                        row = dict(item)
                        row.setdefault("status", "weak")
                        row.setdefault("rationale", "Validation inferred from partial OpenAPI response.")
                        normalized.append(row)
                    else:
                        normalized.append(
                            {
                                "id": f"a{i}",
                                "statement": str(item),
                                "status": "weak",
                                "rationale": "Validation inferred from partial OpenAPI response.",
                            }
                        )
                return normalized

            assumptions = (step_input or {}).get("assumptions")
            if isinstance(assumptions, list) and assumptions:
                synthesized: list[dict[str, Any]] = []
                for i, item in enumerate(assumptions, start=1):
                    if isinstance(item, dict):
                        synthesized.append(
                            {
                                "id": item.get("id", f"a{i}"),
                                "statement": item.get("statement", str(item)),
                                "status": "weak",
                                "confidence": item.get("confidence", 0.5),
                                "rationale": "Validation synthesized from input assumptions due partial OpenAPI mapping.",
                            }
                        )
                    else:
                        synthesized.append(
                            {
                                "id": f"a{i}",
                                "statement": str(item),
                                "status": "weak",
                                "confidence": 0.5,
                                "rationale": "Validation synthesized from input assumptions due partial OpenAPI mapping.",
                            }
                        )
                return synthesized

        if key == "reconciled_constraints":
            inferred = self._find_first_scalar_by_keys(
                raw_response,
                ["reconciled_constraints", "constraints", "reconciled", "resolved_constraints"],
            )
            if isinstance(inferred, list) and inferred:
                normalized: list[dict[str, Any]] = []
                for i, item in enumerate(inferred, start=1):
                    if isinstance(item, dict):
                        row = dict(item)
                        row.setdefault("id", f"rc{i}")
                        row.setdefault("statement", row.get("constraint", f"Constraint {i}"))
                        row.setdefault("precedence", i)
                        normalized.append(row)
                    else:
                        normalized.append({"id": f"rc{i}", "statement": str(item), "precedence": i})
                return normalized

            constraints = (step_input or {}).get("constraints")
            if isinstance(constraints, list) and constraints:
                synthesized: list[dict[str, Any]] = []
                for i, item in enumerate(constraints, start=1):
                    if isinstance(item, dict):
                        statement = self._first_text(item.get("statement"), item.get("constraint"), item.get("text"))
                        synthesized.append(
                            {
                                "id": item.get("id", f"rc{i}"),
                                "statement": statement or f"Constraint {i}",
                                "precedence": i,
                            }
                        )
                    else:
                        synthesized.append({"id": f"rc{i}", "statement": str(item), "precedence": i})
                return synthesized
            return []

        if key.endswith("_summary"):
            if narrative:
                return narrative
            return self._find_first_scalar_by_keys(raw_response, ["summary", "text", "message"])

        if key == "text":
            inferred = self._find_first_scalar_by_keys(raw_response, ["text", "content", "output"])
            text = self._as_text(inferred)
            if text:
                return text
            if narrative:
                return narrative
            raw_text = self._as_text(raw_response)
            if raw_text:
                return raw_text
            return ""

        if key.endswith("_result"):
            if key == "validation_result":
                violations = self._find_first_scalar_by_keys(raw_response, ["violations"])
                satisfied = self._find_first_scalar_by_keys(raw_response, ["satisfied_constraints", "constraints"])
                coverage = self._find_first_scalar_by_keys(raw_response, ["coverage", "pass_rate"])
                status = self._first_text(
                    mapped.get("status"),
                    self._find_first_scalar_by_keys(raw_response, ["status", "result"]),
                )
                if isinstance(violations, list) or isinstance(satisfied, list) or isinstance(coverage, (int, float)):
                    violation_count = len(violations) if isinstance(violations, list) else 0
                    inferred_status = status or ("failed" if violation_count > 0 else "passed")
                    return {
                        "status": inferred_status,
                        "blocking_violations": violation_count,
                        "pass_rate": coverage if isinstance(coverage, (int, float)) else None,
                    }
            status = self._first_text(mapped.get("status"), self._find_first_scalar_by_keys(raw_response, ["status", "result"]))
            if status:
                return status

        if key in {"stored", "updated", "found", "verified", "complete"}:
            if key == "stored":
                has_context_id = bool(
                    mapped.get("context_id")
                    or self._find_first_scalar_by_keys(raw_response, ["context_id", "id"])
                )
                if has_context_id:
                    return True
            if key == "updated":
                inferred = self._find_first_scalar_by_keys(raw_response, ["updated", "updated_state", "applied"])
                if isinstance(inferred, bool):
                    return inferred
                if isinstance(inferred, (int, float)):
                    return bool(inferred)
                if isinstance(inferred, str):
                    lowered = inferred.strip().lower()
                    if lowered in {"true", "yes", "updated", "applied", "success", "ok"}:
                        return True
                    if lowered in {"false", "no", "not_updated", "failed"}:
                        return False
                status = self._first_text(mapped.get("status"), self._find_first_scalar_by_keys(raw_response, ["status"]))
                if status:
                    lowered = status.strip().lower()
                    if lowered in {"success", "ok", "updated", "applied", "done"}:
                        return True
                    if lowered in {"failed", "error", "partial"}:
                        return False
                return True
            if key == "found":
                inferred = self._find_first_scalar_by_keys(raw_response, ["found", "exists", "present"])
                if isinstance(inferred, bool):
                    return inferred
                if isinstance(inferred, (int, float)):
                    return bool(inferred)
                if isinstance(inferred, str):
                    lowered = inferred.strip().lower()
                    if lowered in {"true", "yes", "found", "exists", "present"}:
                        return True
                    if lowered in {"false", "no", "missing", "not_found", "absent"}:
                        return False
                context_value = mapped.get("context")
                if isinstance(context_value, dict) and context_value:
                    status_value = self._first_text(context_value.get("status"), context_value.get("state"))
                    if status_value:
                        lowered = status_value.strip().lower()
                        if lowered in {"found", "present", "available"}:
                            return True
                        if lowered in {"not_found", "missing", "absent"}:
                            return False
                status = self._first_text(mapped.get("status"), self._find_first_scalar_by_keys(raw_response, ["status"]))
                if status:
                    lowered = status.strip().lower()
                    if lowered in {"success", "ok", "found", "present", "available"}:
                        return True
                    if lowered in {"missing", "not_found", "absent", "error"}:
                        return False
                return True
            status = self._first_text(mapped.get("status"), self._find_first_scalar_by_keys(raw_response, ["status"]))
            if status:
                return status.strip().lower() in {"success", "ok", "true", "completed", "done", "found", "verified"}

        if "confidence" in key:
            conf = self._find_first_scalar_by_keys(raw_response, ["confidence", "confidence_score", "score"])
            if isinstance(conf, (int, float)):
                return conf

        return None

    @staticmethod
    def _first_text(*values: Any) -> str | None:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _find_first_scalar_by_keys(self, node: Any, keys: list[str]) -> Any | None:
        wanted = {k.strip().lower() for k in keys if k and k.strip()}
        if not wanted:
            return None

        stack: list[Any] = [node]
        visited = 0
        while stack and visited < 400:
            visited += 1
            current = stack.pop()

            if isinstance(current, dict):
                for key, value in current.items():
                    if isinstance(key, str) and key.strip().lower() in wanted:
                        if value is not None:
                            return value
                    if isinstance(value, (dict, list)):
                        stack.append(value)
                continue

            if isinstance(current, list):
                for item in current:
                    if isinstance(item, (dict, list)):
                        stack.append(item)

        return None

    def _resolve_response_reference(
        self,
        value: str,
        *,
        raw_response: Any,
        binding: BindingSpec,
        step_input: dict[str, Any] | None,
        request_payload: dict[str, Any] | None,
    ) -> Any:
        if "." not in value:
            return value

        namespace, field_path = value.split(".", 1)

        if not field_path:
            raise ResponseMappingError(
                f"Binding '{binding.id}' contains an invalid response reference '{value}'.",
                capability_id=binding.capability_id,
            )

        if namespace == "response":
            return self._resolve_path(
                root=raw_response,
                field_path=field_path,
                binding=binding,
                namespace=namespace,
            )

        if namespace == "input":
            if step_input is None:
                raise ResponseMappingError(
                    f"Binding '{binding.id}' cannot resolve '{value}' because step input is unavailable.",
                    capability_id=binding.capability_id,
                )
            return self._resolve_path(
                root=step_input,
                field_path=field_path,
                binding=binding,
                namespace=namespace,
            )

        if namespace == "request":
            if request_payload is None:
                raise ResponseMappingError(
                    f"Binding '{binding.id}' cannot resolve '{value}' because request payload is unavailable.",
                    capability_id=binding.capability_id,
                )
            return self._resolve_path(
                root=request_payload,
                field_path=field_path,
                binding=binding,
                namespace=namespace,
            )

        return value

    def _resolve_with_fallbacks(
        self,
        *,
        response_refs: list[Any],
        raw_response: Any,
        binding: BindingSpec,
        step_input: dict[str, Any] | None,
        request_payload: dict[str, Any] | None,
    ) -> Any:
        last_error: ResponseMappingError | None = None

        for item in response_refs:
            if not isinstance(item, str) or not item:
                continue
            try:
                return self._resolve_response_reference(
                    item,
                    raw_response=raw_response,
                    binding=binding,
                    step_input=step_input,
                    request_payload=request_payload,
                )
            except ResponseMappingError as exc:
                last_error = exc
                continue

        if last_error is not None:
            raise last_error

        raise ResponseMappingError(
            f"Binding '{binding.id}' fallback response mapping list contains no usable references.",
            capability_id=binding.capability_id,
        )

    def _resolve_path(
        self,
        *,
        root: Any,
        field_path: str,
        binding: BindingSpec,
        namespace: str,
    ) -> Any:
        current: Any = root
        parts = field_path.split(".")

        for index, part in enumerate(parts):
            if not part:
                raise ResponseMappingError(
                    f"Binding '{binding.id}' contains an invalid {namespace} path '{namespace}.{field_path}'.",
                    capability_id=binding.capability_id,
                )

            if isinstance(current, dict):
                if part not in current:
                    if namespace == "response":
                        # Recover from common provider key drift in OpenAPI JSON outputs.
                        fallback_key = self._find_response_fallback_key(
                            expected_key=part,
                            current=current,
                        )
                        if fallback_key is not None:
                            current = current[fallback_key]
                            continue

                    if (
                        namespace == "response"
                        and index == len(parts) - 1
                        and part == "output"
                    ):
                        return current
                    if (
                        namespace == "response"
                        and index == len(parts) - 1
                        and part == "warnings"
                    ):
                        return []
                    raise ResponseMappingError(
                        f"Binding '{binding.id}' references missing {namespace} field '{namespace}.{field_path}'.",
                        capability_id=binding.capability_id,
                    )
                current = current[part]
                continue

            if isinstance(current, list):
                if not part.isdigit():
                    raise ResponseMappingError(
                        f"Binding '{binding.id}' cannot resolve '{namespace}.{field_path}' because '{part}' is not a valid list index.",
                        capability_id=binding.capability_id,
                    )

                idx = int(part)
                if idx < 0 or idx >= len(current):
                    raise ResponseMappingError(
                        f"Binding '{binding.id}' references out-of-range list index '{part}' in '{namespace}.{field_path}'.",
                        capability_id=binding.capability_id,
                    )

                current = current[idx]
                continue

            raise ResponseMappingError(
                f"Binding '{binding.id}' cannot resolve '{namespace}.{field_path}' because '{part}' is accessed on a non-mapping value.",
                capability_id=binding.capability_id,
            )

        return current

    def _find_response_fallback_key(
        self,
        *,
        expected_key: str,
        current: dict[str, Any],
    ) -> str | None:
        if not current:
            return None

        if expected_key == "content_json":
            if "content_json" in current:
                return "content_json"
            if "content" in current and isinstance(current.get("content"), str):
                try:
                    parsed = json.loads(current["content"])
                    if isinstance(parsed, dict):
                        current["content_json"] = parsed
                        return "content_json"
                except Exception:
                    pass

        lower_to_actual = {
            str(key).strip().lower(): key for key in current.keys() if isinstance(key, str)
        }

        # Direct synonym candidates for common model variations.
        candidates = self._candidate_keys(expected_key)
        for cand in candidates:
            actual = lower_to_actual.get(cand)
            if actual is not None:
                return actual

        expected_tokens = set(self._tokenize(expected_key))
        if not expected_tokens:
            return None

        best_key: str | None = None
        best_score = 0
        for key in lower_to_actual.keys():
            key_tokens = set(self._tokenize(key))
            if not key_tokens:
                continue
            score = len(expected_tokens & key_tokens)
            if score > best_score:
                best_score = score
                best_key = key

        if best_key is not None and best_score >= 1:
            return lower_to_actual[best_key]

        return None

    @staticmethod
    def _tokenize(value: str) -> list[str]:
        return [t for t in re.split(r"[^a-z0-9]+", value.lower()) if t]

    def _candidate_keys(self, expected_key: str) -> list[str]:
        candidates: list[str] = []
        key = expected_key.strip().lower()
        if not key:
            return candidates

        candidates.append(key)

        if key.endswith("_rationale"):
            candidates.extend(["rationale", "reasoning", "explanation"])
        if key.endswith("_result"):
            candidates.extend(["result", "validation", "evaluation"])
        if key.endswith("_score"):
            candidates.extend(["score", "confidence", "confidence_score"])
        if key.endswith("_summary"):
            candidates.extend(["summary", "text"])
        if key.endswith("s") and len(key) > 3:
            candidates.append(key[:-1])

        for prefix in (
            "selected_",
            "selection_",
            "validated_",
            "validation_",
            "ranked_",
            "scored_",
            "prioritized_",
            "reconciled_",
            "structured_",
            "summary_",
        ):
            if key.startswith(prefix) and len(key) > len(prefix):
                candidates.append(key[len(prefix) :])

        # De-duplicate while keeping order.
        return list(dict.fromkeys(candidates))
