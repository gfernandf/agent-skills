"""Step-level control-flow primitives.

This module provides six composable control-flow primitives that extend the
step execution model without touching the DAG scheduler.  The scheduler sees
every step exactly once; control flow (iteration, branching, retry) is
resolved *inside* the step execution by this module.

Primitives
──────────
1. **condition**  — skip a step when a boolean expression is false.
2. **retry**      — retry a failed invocation with configurable backoff.
3. **foreach**    — iterate over a collection, executing the capability once
                    per item and collecting outputs as lists.
4. **while_loop** — re-execute the capability while a condition holds (bounded).
5. **router**     — dynamic branching: pick which capability to run based on
                    an expression evaluated at runtime.
6. **scatter**    — fan-out: run N capabilities in parallel on the same input
                    and merge their results.

Composition rules
─────────────────
- ``condition`` gates everything: if false, the step is skipped immediately.
- ``retry`` wraps each single invocation (including each foreach iteration).
- ``foreach`` and ``while`` are mutually exclusive (both are iteration).
- ``retry`` composes with ``foreach`` (each iteration can be retried).
- ``router`` resolves the capability *before* invocation; composes with
  ``condition``, ``retry``, ``foreach``, and ``while``.
- ``scatter`` is mutually exclusive with ``foreach``, ``while``, and
  ``router`` (scatter manages its own capability list).

Config keys recognised in ``step.config``
──────────────────────────────────────────
.. code-block:: yaml

   config:
     # Gate — skip step when condition is false
     condition: "vars.risk_level == 'high'"

     # Retry — retry on failure
     retry:
       max_attempts: 3               # required, >= 1
       backoff_seconds: 1.0          # initial wait (default 1)
       backoff_multiplier: 2.0       # exponential growth (default 2)

     # Foreach — iterate a list
     foreach:
       items: "vars.documents"       # expression → list
       as: "item"                    # injected into vars
       index_as: "idx"              # optional, injected into vars

     # While — conditional loop
     while:
       condition: "vars.score < 0.8" # re-evaluated each iteration
       max_iterations: 10            # required safety bound

     # Router — dynamic capability selection
     router:
       on: "vars.doc_type"            # expression → value to match
       cases:
         invoice: "doc.invoice.parse"
         contract: "doc.contract.analyze"
       default: "doc.generic.process"  # optional fallback

     # Scatter — parallel fan-out + merge
     scatter:
       capabilities:
         - "text.content.summarize"
         - "analysis.theme.cluster"
         - "analysis.risk.extract"
       merge: "collect"               # collect | concat_lists | first_success
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from runtime.step_expression import ExpressionError, evaluate, evaluate_bool


# ── Parsed config structures ─────────────────────────────────────────────────


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    backoff_seconds: float
    backoff_multiplier: float

    @classmethod
    def from_config(cls, raw: Any) -> RetryPolicy | None:
        if not isinstance(raw, dict):
            return None
        max_attempts = raw.get("max_attempts", 3)
        if not isinstance(max_attempts, int) or max_attempts < 1:
            max_attempts = 3
        return cls(
            max_attempts=max_attempts,
            backoff_seconds=float(raw.get("backoff_seconds", 1.0)),
            backoff_multiplier=float(raw.get("backoff_multiplier", 2.0)),
        )


@dataclass(frozen=True)
class ForeachConfig:
    items_expr: str
    as_var: str
    index_var: str | None

    @classmethod
    def from_config(cls, raw: Any) -> ForeachConfig | None:
        if not isinstance(raw, dict):
            return None
        items = raw.get("items")
        as_var = raw.get("as", "item")
        if not isinstance(items, str) or not items.strip():
            return None
        return cls(
            items_expr=items.strip(),
            as_var=as_var,
            index_var=raw.get("index_as"),
        )


@dataclass(frozen=True)
class WhileConfig:
    condition_expr: str
    max_iterations: int

    @classmethod
    def from_config(cls, raw: Any) -> WhileConfig | None:
        if not isinstance(raw, dict):
            return None
        condition = raw.get("condition")
        max_iter = raw.get("max_iterations", 10)
        if not isinstance(condition, str) or not condition.strip():
            return None
        if not isinstance(max_iter, int) or max_iter < 1:
            max_iter = 10
        return cls(
            condition_expr=condition.strip(),
            max_iterations=max_iter,
        )


@dataclass(frozen=True)
class RouterConfig:
    on_expr: str
    cases: dict[str, str]  # value → capability_id
    default: str | None

    @classmethod
    def from_config(cls, raw: Any) -> RouterConfig | None:
        if not isinstance(raw, dict):
            return None
        on = raw.get("on")
        if not isinstance(on, str) or not on.strip():
            return None
        cases = raw.get("cases")
        if not isinstance(cases, dict) or not cases:
            return None
        # Validate all case values are strings
        clean_cases = {}
        for k, v in cases.items():
            if isinstance(v, str) and v.strip():
                clean_cases[str(k)] = v.strip()
        if not clean_cases:
            return None
        default = raw.get("default")
        if isinstance(default, str) and default.strip():
            default = default.strip()
        else:
            default = None
        return cls(
            on_expr=on.strip(),
            cases=clean_cases,
            default=default,
        )


@dataclass(frozen=True)
class ScatterConfig:
    capabilities: list[str]
    merge: str  # "collect" | "concat_lists" | "first_success"

    _VALID_MERGE = frozenset({"collect", "concat_lists", "first_success"})

    @classmethod
    def from_config(cls, raw: Any) -> ScatterConfig | None:
        if not isinstance(raw, dict):
            return None
        caps = raw.get("capabilities")
        if not isinstance(caps, list) or len(caps) < 2:
            return None
        clean_caps = [c.strip() for c in caps if isinstance(c, str) and c.strip()]
        if len(clean_caps) < 2:
            return None
        merge = raw.get("merge", "collect")
        if not isinstance(merge, str) or merge not in cls._VALID_MERGE:
            merge = "collect"
        return cls(capabilities=clean_caps, merge=merge)


# ── Control flow helpers ─────────────────────────────────────────────────────


class StepSkipped(Exception):
    """Raised to signal the step should be skipped (condition was false)."""


def check_condition(config: dict[str, Any], state) -> bool:
    """Evaluate step condition.  Returns True if step should execute.

    Raises StepSkipped if the condition is present and evaluates to False.
    """
    condition = config.get("condition")
    if condition is None:
        return True
    if not isinstance(condition, str):
        return True
    result = evaluate_bool(condition, state)
    if not result:
        raise StepSkipped(f"Condition not met: {condition}")
    return True


InvokeFn = Callable[[], tuple[dict[str, Any], dict[str, Any] | None]]
"""Callable that invokes the capability once, returns (produced, meta)."""


def invoke_with_retry(
    invoke_fn: InvokeFn,
    retry: RetryPolicy | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Call invoke_fn, retrying on failure according to the retry policy.

    Returns (produced, meta) on success.
    Raises the last exception on exhaustion.
    """
    if retry is None:
        return invoke_fn()

    last_error: Exception | None = None
    wait = retry.backoff_seconds

    for attempt in range(retry.max_attempts):
        try:
            return invoke_fn()
        except Exception as e:
            last_error = e
            if attempt < retry.max_attempts - 1:
                time.sleep(wait)
                wait *= retry.backoff_multiplier
    raise last_error  # type: ignore[misc]


def execute_foreach(
    foreach: ForeachConfig,
    state,
    invoke_fn: Callable[[dict[str, Any]], tuple[dict[str, Any], dict[str, Any] | None]],
    retry: RetryPolicy | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Execute a capability once per item in the resolved list.

    ``invoke_fn(extra_vars)`` receives a dict of loop variables to inject
    into step_input before each invocation.

    Returns collected outputs: each output key maps to a list of per-item values.
    Meta is from the last iteration (or aggregated attempts).
    """
    items = evaluate(foreach.items_expr, state)
    if not isinstance(items, (list, tuple)):
        raise ExpressionError(
            f"foreach items expression '{foreach.items_expr}' "
            f"resolved to {type(items).__name__}, expected list."
        )

    collected_outputs: dict[str, list[Any]] = {}
    last_meta: dict[str, Any] | None = None
    total_attempts = 0

    for idx, item in enumerate(items):
        loop_vars: dict[str, Any] = {foreach.as_var: item}
        if foreach.index_var:
            loop_vars[foreach.index_var] = idx

        produced, meta = invoke_with_retry(
            lambda _lv=loop_vars: invoke_fn(_lv),
            retry,
        )

        # Collect outputs as lists
        if isinstance(produced, dict):
            for key, value in produced.items():
                collected_outputs.setdefault(key, []).append(value)

        if isinstance(meta, dict):
            last_meta = meta
            total_attempts += len(meta.get("attempts", []))

    # Build aggregated meta
    agg_meta = dict(last_meta) if last_meta else {}
    agg_meta["foreach_count"] = len(items)
    agg_meta["foreach_total_attempts"] = total_attempts

    return collected_outputs, agg_meta


def execute_while(
    while_cfg: WhileConfig,
    state,
    invoke_fn: InvokeFn,
    apply_output_fn: Callable[[dict[str, Any]], None],
    retry: RetryPolicy | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Execute a capability repeatedly while a condition holds.

    ``apply_output_fn(produced)`` is called after each iteration to write
    intermediate outputs to state so the condition can reference them.

    Returns the outputs from the last iteration.
    """
    last_produced: dict[str, Any] = {}
    last_meta: dict[str, Any] | None = None
    iterations = 0

    for iteration in range(while_cfg.max_iterations):
        # Check condition (first iteration always runs if we got here)
        if iteration > 0:
            if not evaluate_bool(while_cfg.condition_expr, state):
                break

        produced, meta = invoke_with_retry(invoke_fn, retry)
        last_produced = produced if isinstance(produced, dict) else {}
        last_meta = meta
        iterations += 1

        # Apply intermediate outputs so next condition check sees them
        apply_output_fn(last_produced)

    agg_meta = dict(last_meta) if last_meta else {}
    agg_meta["while_iterations"] = iterations
    agg_meta["while_condition"] = while_cfg.condition_expr
    agg_meta["while_exhausted"] = iterations >= while_cfg.max_iterations

    return last_produced, agg_meta


# ── Router ───────────────────────────────────────────────────────────────────


def resolve_router(
    router: RouterConfig,
    state,
) -> tuple[str, dict[str, Any]]:
    """Evaluate the router expression and return the resolved capability_id.

    Returns ``(capability_id, meta)`` where *meta* contains the matched case
    key (or ``"__default__"``).

    Raises ``ExpressionError`` if no case matches and no default is provided.
    """
    value = evaluate(router.on_expr, state)
    matched_key = str(value) if value is not None else None

    if matched_key is not None and matched_key in router.cases:
        return router.cases[matched_key], {"router_matched": matched_key}

    if router.default is not None:
        return router.default, {"router_matched": "__default__"}

    raise ExpressionError(
        f"Router expression '{router.on_expr}' resolved to "
        f"'{matched_key}' which has no matching case and no default."
    )


# ── Scatter-Gather ───────────────────────────────────────────────────────────


def execute_scatter(
    scatter: ScatterConfig,
    invoke_fn: Callable[[str], tuple[dict[str, Any], dict[str, Any] | None]],
    retry: RetryPolicy | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Fan-out: run multiple capabilities in parallel and merge results.

    ``invoke_fn(capability_id)`` executes one capability and returns
    ``(produced, meta)``.

    Merge strategies:
    - ``collect`` — output is ``{capability_id: produced, ...}``
    - ``concat_lists`` — merge list-valued outputs across capabilities
    - ``first_success`` — return first successful result, cancel the rest

    Returns ``(merged_output, aggregated_meta)``.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    cap_ids = scatter.capabilities

    def _run(
        cap_id: str,
    ) -> tuple[str, dict[str, Any], dict[str, Any] | None, Exception | None]:
        try:
            produced, meta = invoke_with_retry(lambda: invoke_fn(cap_id), retry)
            return cap_id, produced, meta, None
        except Exception as exc:
            return cap_id, {}, None, exc

    results: dict[str, tuple[dict[str, Any], dict[str, Any] | None]] = {}
    errors: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=len(cap_ids)) as pool:
        futures = {pool.submit(_run, cid): cid for cid in cap_ids}

        if scatter.merge == "first_success":
            for future in as_completed(futures):
                cap_id, produced, meta, error = future.result()
                if error is None:
                    # Cancel remaining futures
                    for f in futures:
                        f.cancel()
                    return produced, {
                        "scatter_strategy": "first_success",
                        "scatter_count": len(cap_ids),
                        "scatter_winner": cap_id,
                    }
                errors[cap_id] = str(error)
            # All failed
            raise ExpressionError(
                f"Scatter first_success: all {len(cap_ids)} capabilities "
                f"failed. Errors: {errors}"
            )
        else:
            for future in as_completed(futures):
                cap_id, produced, meta, error = future.result()
                if error is not None:
                    errors[cap_id] = str(error)
                else:
                    results[cap_id] = (produced, meta)

    # Merge
    if scatter.merge == "collect":
        merged: dict[str, Any] = {}
        for cap_id in cap_ids:
            if cap_id in results:
                merged[cap_id] = results[cap_id][0]
            # failed capabilities are absent from merged output
    elif scatter.merge == "concat_lists":
        merged = {}
        for cap_id in cap_ids:
            if cap_id not in results:
                continue
            produced = results[cap_id][0]
            if isinstance(produced, dict):
                for k, v in produced.items():
                    existing = merged.get(k)
                    if isinstance(existing, list) and isinstance(v, list):
                        existing.extend(v)
                    elif isinstance(v, list):
                        merged[k] = list(v)
                    else:
                        merged.setdefault(k, []).append(v)
    else:
        merged = {}

    agg_meta: dict[str, Any] = {
        "scatter_strategy": scatter.merge,
        "scatter_count": len(cap_ids),
        "scatter_succeeded": len(results),
        "scatter_failed": len(errors),
    }
    if errors:
        agg_meta["scatter_errors"] = errors

    return merged, agg_meta
