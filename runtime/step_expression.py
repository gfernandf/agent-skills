"""Safe expression evaluator for step control-flow conditions.

Grammar (recursive descent)
────────────────────────────
    expr      := or_expr
    or_expr   := and_expr ('or' and_expr)*
    and_expr  := not_expr ('and' not_expr)*
    not_expr  := 'not' not_expr | cmp_expr
    cmp_expr  := value (('==' | '!=' | '>' | '<' | '>=' | '<=' | 'in' | 'not in') value)?
    value     := ref | string | number | bool | null | list | '(' expr ')'
    ref       := identifier ('.' identifier)*
    list      := '[' (expr (',' expr)*)? ']'
    string    := "'" [^']* "'" | '"' [^"]* '"'
    number    := [0-9]+ ('.' [0-9]+)?
    bool      := 'true' | 'false'
    null      := 'null' | 'none'
    identifier := [a-zA-Z_][a-zA-Z0-9_]*

Resolved references
───────────────────
References like ``vars.score``, ``inputs.language``, ``outputs.summary`` are
resolved against the live :class:`ExecutionState` using the same namespace
rules as the input mapper (inputs.*, vars.*, outputs.*, working.*, frame.*,
output.*, extensions.*).

Security: **No** use of ``eval``, ``exec``, or ``compile`` builtins.  Only
comparison operators and boolean logic are supported.
"""

from __future__ import annotations

import re
from typing import Any

# ── Tokeniser ────────────────────────────────────────────────────────────────

_TOKEN_SPEC = [
    ("NUMBER", r"\d+(?:\.\d+)?"),
    ("STRING", r"'[^']*'|\"[^\"]*\""),
    ("BOOL", r"\b(?:true|false)\b"),
    ("NULL", r"\b(?:null|none)\b"),
    ("NOT_IN", r"\bnot\s+in\b"),
    ("OP", r"==|!=|>=|<=|>|<"),
    ("AND", r"\band\b"),
    ("OR", r"\bor\b"),
    ("NOT", r"\bnot\b"),
    ("IN", r"\bin\b"),
    ("IDENT", r"[a-zA-Z_][a-zA-Z0-9_]*"),
    ("DOT", r"\."),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("LBRACKET", r"\["),
    ("RBRACKET", r"\]"),
    ("COMMA", r","),
    ("SKIP", r"\s+"),
]

_TOKEN_RE = re.compile("|".join(f"(?P<{name}>{pat})" for name, pat in _TOKEN_SPEC))


class _Token:
    __slots__ = ("kind", "value")

    def __init__(self, kind: str, value: str) -> None:
        self.kind = kind
        self.value = value

    def __repr__(self) -> str:
        return f"Token({self.kind}, {self.value!r})"


def _tokenise(source: str) -> list[_Token]:
    tokens: list[_Token] = []
    for m in _TOKEN_RE.finditer(source):
        kind = m.lastgroup
        if kind == "SKIP":
            continue
        tokens.append(_Token(kind, m.group()))  # type: ignore[arg-type]
    return tokens


# ── Parser ───────────────────────────────────────────────────────────────────


class ExpressionError(Exception):
    """Raised on parse or type errors in a step expression."""


class _Parser:
    """Recursive-descent parser that produces an AST of tuples."""

    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> _Token | None:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _advance(self) -> _Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expect(self, kind: str) -> _Token:
        tok = self._peek()
        if tok is None or tok.kind != kind:
            raise ExpressionError(f"Expected {kind}, got {tok}")
        return self._advance()

    # ── Grammar rules ──────────────────────────────────────────────────

    def parse(self):
        node = self._or_expr()
        if self._pos < len(self._tokens):
            raise ExpressionError(f"Unexpected token: {self._tokens[self._pos]}")
        return node

    def _or_expr(self):
        left = self._and_expr()
        while self._peek() and self._peek().kind == "OR":
            self._advance()
            right = self._and_expr()
            left = ("or", left, right)
        return left

    def _and_expr(self):
        left = self._not_expr()
        while self._peek() and self._peek().kind == "AND":
            self._advance()
            right = self._not_expr()
            left = ("and", left, right)
        return left

    def _not_expr(self):
        if self._peek() and self._peek().kind == "NOT":
            self._advance()
            operand = self._not_expr()
            return ("not", operand)
        return self._cmp_expr()

    def _cmp_expr(self):
        left = self._value()
        tok = self._peek()
        if tok and tok.kind == "OP":
            op = self._advance().value
            right = self._value()
            return ("cmp", op, left, right)
        if tok and tok.kind == "IN":
            self._advance()
            right = self._value()
            return ("cmp", "in", left, right)
        if tok and tok.kind == "NOT_IN":
            self._advance()
            right = self._value()
            return ("cmp", "not in", left, right)
        return left

    def _value(self):
        tok = self._peek()
        if tok is None:
            raise ExpressionError("Unexpected end of expression")

        if tok.kind == "NUMBER":
            self._advance()
            return ("literal", float(tok.value) if "." in tok.value else int(tok.value))
        if tok.kind == "STRING":
            self._advance()
            return ("literal", tok.value[1:-1])
        if tok.kind == "BOOL":
            self._advance()
            return ("literal", tok.value == "true")
        if tok.kind == "NULL":
            self._advance()
            return ("literal", None)
        if tok.kind == "LPAREN":
            self._advance()
            node = self._or_expr()
            self._expect("RPAREN")
            return node
        if tok.kind == "LBRACKET":
            return self._list_literal()
        if tok.kind == "IDENT":
            return self._ref()

        raise ExpressionError(f"Unexpected token: {tok}")

    def _ref(self):
        parts = [self._advance().value]
        while self._peek() and self._peek().kind == "DOT":
            self._advance()
            parts.append(self._expect("IDENT").value)
        if len(parts) == 1:
            # Bare identifier — treat as literal string? No, treat as ref.
            pass
        return ("ref", tuple(parts))

    def _list_literal(self):
        self._advance()  # consume '['
        items: list = []
        if self._peek() and self._peek().kind != "RBRACKET":
            items.append(self._or_expr())
            while self._peek() and self._peek().kind == "COMMA":
                self._advance()
                items.append(self._or_expr())
        self._expect("RBRACKET")
        return ("list", tuple(items))


# ── Evaluator ────────────────────────────────────────────────────────────────


def _resolve_ref(parts: tuple[str, ...], state) -> Any:
    """Resolve a dotted reference against ExecutionState.

    Uses the same namespace semantics as the runtime reference resolver:
    inputs.*, vars.*, outputs.*, frame.*, working.*, output.*, extensions.*.
    """
    if not parts:
        return None
    namespace = parts[0]
    rest = parts[1:]

    # Top-level namespace dispatch
    container: Any
    if namespace == "inputs":
        container = state.inputs
    elif namespace == "vars":
        container = state.vars
    elif namespace == "outputs":
        container = state.outputs
    elif namespace == "frame":
        container = state.frame
    elif namespace == "working":
        container = state.working
    elif namespace == "output":
        container = state.output
    elif namespace == "extensions":
        container = state.extensions
    else:
        # Single bare identifier — check vars first, then treat as missing
        if hasattr(state, "vars") and namespace in state.vars:
            return state.vars[namespace]
        return None

    # Walk remaining path
    for segment in rest:
        if container is None:
            return None
        if isinstance(container, dict):
            container = container.get(segment)
        elif hasattr(container, segment):
            container = getattr(container, segment)
        elif isinstance(container, (list, tuple)):
            try:
                container = container[int(segment)]
            except (IndexError, ValueError):
                return None
        else:
            return None
    return container


def _eval_node(node, state) -> Any:
    """Recursively evaluate an AST node."""
    tag = node[0]

    if tag == "literal":
        return node[1]

    if tag == "ref":
        return _resolve_ref(node[1], state)

    if tag == "list":
        return [_eval_node(item, state) for item in node[1]]

    if tag == "not":
        return not _eval_node(node[1], state)

    if tag == "and":
        return _eval_node(node[1], state) and _eval_node(node[2], state)

    if tag == "or":
        return _eval_node(node[1], state) or _eval_node(node[2], state)

    if tag == "cmp":
        op = node[1]
        left = _eval_node(node[2], state)
        right = _eval_node(node[3], state)
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == "in":
            return left in right if right is not None else False
        if op == "not in":
            return left not in right if right is not None else True
        # Numeric comparisons — gracefully handle non-numeric
        try:
            l, r = float(left), float(right)
        except (TypeError, ValueError):
            return False
        if op == ">":
            return l > r
        if op == "<":
            return l < r
        if op == ">=":
            return l >= r
        if op == "<=":
            return l <= r

    raise ExpressionError(f"Unknown AST node: {tag}")


# ── Public API ───────────────────────────────────────────────────────────────


def evaluate(expression: str, state) -> Any:
    """Evaluate a step expression against the current execution state.

    Returns the result — typically a bool for conditions, but can be any value.

    Raises :class:`ExpressionError` on syntax or evaluation errors.
    """
    if not expression or not expression.strip():
        raise ExpressionError("Empty expression")
    tokens = _tokenise(expression.strip())
    if not tokens:
        raise ExpressionError("Empty expression after tokenisation")
    ast = _Parser(tokens).parse()
    return _eval_node(ast, state)


def evaluate_bool(expression: str, state) -> bool:
    """Evaluate an expression and coerce the result to bool."""
    return bool(evaluate(expression, state))
