"""Scopus-subset query parser.

Parses the narrow Scopus-DSL subset used in ``data/search_terms/**/*.txt`` into a
neutral term tree, separating content terms from date filters.

Supported grammar
-----------------
- Field ops: ``TITLE-ABS-KEY ( <term> )``, ``TITLE-ABS-KEY-AUTH ( <term> )``.
  ``<term>`` is free text (may be multi-word, unquoted), optionally quoted.
- Boolean: ``AND``, ``OR``, with parentheses for grouping/nesting.
- Date filters (parsed out separately, not part of the term tree):
  - ``PUBYEAR > N``, ``PUBYEAR < N``, ``PUBYEAR AFT N``.
  - ``ORIG-LOAD-DATE AFT <epoch>``, ``ORIG-LOAD-DATE BEF <epoch>`` → discarded.

Operator precedence mirrors Scopus: ``OR`` is evaluated before ``AND``, so
``a AND b OR c`` parses as ``a AND (b OR c)``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

_FieldOp = Literal["TITLE-ABS-KEY", "TITLE-ABS-KEY-AUTH"]
_DateField = Literal["PUBYEAR", "ORIG-LOAD-DATE"]
_Operator = Literal[">", "<", "AFT", "BEF"]


class UnsupportedScopusSyntax(Exception):
    """Raised when a query uses syntax outside the supported subset."""

    def __init__(self, term_name: str, detail: str) -> None:
        self.term_name = term_name
        self.detail = detail
        super().__init__(f"{term_name}: {detail}")


@dataclass
class Field:
    """A single field-operator term, e.g. ``TITLE-ABS-KEY(game model)``."""

    op: _FieldOp
    term: str

    def __repr__(self) -> str:
        short = "TAK" if self.op == "TITLE-ABS-KEY" else "TAK-AUTH"
        return f"{short}({self.term})"


@dataclass
class And:
    """Boolean AND node."""

    children: list[Node]

    def __repr__(self) -> str:
        return f"AND[{', '.join(repr(c) for c in self.children)}]"


@dataclass
class Or:
    """Boolean OR node."""

    children: list[Node]

    def __repr__(self) -> str:
        return f"OR[{', '.join(repr(c) for c in self.children)}]"


@dataclass
class DateFilter:
    """A raw date clause as it appeared in the query."""

    field: _DateField
    op: _Operator
    value: int

    def __repr__(self) -> str:
        return f"DATE[{self.field} {self.op} {self.value}]"


Node = Field | And | Or | DateFilter


@dataclass
class ParsedQuery:
    """Neutral representation of a parsed Scopus-subset query."""

    tree: Node
    pubyear_from: int | None = None
    pubyear_to: int | None = None
    terms: list[str] = field(default_factory=list)


# Tokenizer -------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    \s*
    (
        \(|
        \)|
        TITLE-ABS-KEY-AUTH|
        TITLE-ABS-KEY|
        ORIG-LOAD-DATE|
        PUBYEAR|
        AND|
        OR|
        AFT|
        BEF|
        >|<|
        \d+|
        [^\s()]+   # any other word/token, including quoted text
    )
    """,
    re.VERBOSE,
)

_TOKEN_TYPES: dict[str, str] = {
    "TITLE-ABS-KEY": "FIELD",
    "TITLE-ABS-KEY-AUTH": "FIELD",
    "ORIG-LOAD-DATE": "ORIG_LOAD_DATE",
    "PUBYEAR": "PUBYEAR",
    "AND": "AND",
    "OR": "OR",
    "AFT": "AFT",
    "BEF": "BEF",
    ">": "GT",
    "<": "LT",
    "(": "LPAREN",
    ")": "RPAREN",
}


@dataclass(frozen=True)
class _Token:
    type: str
    value: str


def _tokenize(query: str, term_name: str) -> list[_Token]:
    """Split ``query`` into a flat token list."""
    # Normalize Unicode whitespace (including non-breaking spaces) to a single
    # ASCII space so the tokenizer can treat all whitespace uniformly.
    normalized = re.sub(r"\s+", " ", query).strip()
    if not normalized:
        raise UnsupportedScopusSyntax(term_name, "query is empty")

    tokens: list[_Token] = []
    pos = 0
    while pos < len(normalized):
        match = _TOKEN_RE.match(normalized, pos)
        if not match:
            snippet = normalized[pos : pos + 40]
            raise UnsupportedScopusSyntax(term_name, f"unexpected characters: {snippet!r}")
        raw = match.group(1)
        if raw.isdigit():
            tokens.append(_Token("NUMBER", raw))
        else:
            tok_type = _TOKEN_TYPES.get(raw, "WORD")
            tokens.append(_Token(tok_type, raw))
        pos = match.end()
    return tokens


# Parser ----------------------------------------------------------------------


class _Parser:
    def __init__(self, tokens: list[_Token], term_name: str) -> None:
        self.tokens = tokens
        self.term_name = term_name
        self.pos = 0

    # ---- utilities ---------------------------------------------------------
    def _peek(self, offset: int = 0) -> _Token | None:
        idx = self.pos + offset
        return self.tokens[idx] if idx < len(self.tokens) else None

    def _consume(self, expected_type: str) -> _Token:
        tok = self._peek()
        if tok is None:
            raise UnsupportedScopusSyntax(
                self.term_name, f"expected {expected_type} but reached end of query"
            )
        if tok.type != expected_type:
            raise UnsupportedScopusSyntax(
                self.term_name,
                f"expected {expected_type}, got {tok.type}({tok.value!r})",
            )
        self.pos += 1
        return tok

    def _consume_any(self) -> _Token:
        tok = self._peek()
        if tok is None:
            raise UnsupportedScopusSyntax(self.term_name, "expected token but reached end of query")
        self.pos += 1
        return tok

    # ---- grammar -----------------------------------------------------------
    def parse(self) -> Node:
        node = self._expr()
        if self.pos < len(self.tokens):
            leftover = self.tokens[self.pos :]
            snippet = " ".join(t.value for t in leftover[:8])
            raise UnsupportedScopusSyntax(
                self.term_name, f"unexpected trailing tokens: {snippet!r}"
            )
        return node

    def _expr(self) -> Node:
        """AND-expression: OR-expr {AND OR-expr}*."""
        children = [self._or_expr()]
        while self._peek() and self._peek().type == "AND":
            self._consume("AND")
            children.append(self._or_expr())
        return _simplify(And, children)

    def _or_expr(self) -> Node:
        """OR-expression: primary {OR primary}*."""
        children = [self._primary()]
        while self._peek() and self._peek().type == "OR":
            self._consume("OR")
            children.append(self._primary())
        return _simplify(Or, children)

    def _primary(self) -> Node:
        tok = self._peek()
        if tok is None:
            raise UnsupportedScopusSyntax(
                self.term_name, "expected term or group but reached end of query"
            )

        if tok.type == "LPAREN":
            self._consume("LPAREN")
            node = self._expr()
            self._consume("RPAREN")
            return node

        if tok.type == "FIELD":
            return self._field(tok.value)

        if tok.type == "PUBYEAR":
            return self._date_clause("PUBYEAR")

        if tok.type == "ORIG_LOAD_DATE":
            return self._date_clause("ORIG-LOAD-DATE")

        raise UnsupportedScopusSyntax(
            self.term_name,
            f"unsupported field/operator {tok.value!r}",
        )

    def _field(self, op: _FieldOp) -> Field:
        self._consume("FIELD")
        self._consume("LPAREN")
        parts: list[str] = []
        while self._peek() and self._peek().type != "RPAREN":
            parts.append(self._consume_any().value)
        if not parts:
            raise UnsupportedScopusSyntax(self.term_name, f"empty term in {op}")
        self._consume("RPAREN")
        return Field(op, " ".join(parts))

    def _date_clause(self, field: _DateField) -> DateFilter:
        self._consume(field if field == "PUBYEAR" else "ORIG_LOAD_DATE")
        op_tok = self._peek()
        if op_tok is None or op_tok.type not in {"GT", "LT", "AFT", "BEF"}:
            got = op_tok.value if op_tok else "end of query"
            raise UnsupportedScopusSyntax(
                self.term_name,
                f"expected date operator after {field}, got {got!r}",
            )
        self._consume(op_tok.type)
        val_tok = self._consume("NUMBER")
        return DateFilter(field, op_tok.value, int(val_tok.value))


def _simplify(ctor: type[And] | type[Or], children: list[Node]) -> Node:
    """Drop single-child boolean nodes; keep the child directly."""
    if len(children) == 1:
        return children[0]
    return ctor(children)


# Post-processing -----------------------------------------------------------


def _extract_dates(node: Node) -> tuple[Node | None, list[DateFilter]]:
    """Return the tree with DateFilter nodes removed plus the collected dates."""
    if isinstance(node, DateFilter):
        return None, [node]
    if isinstance(node, Field):
        return node, []

    kept: list[Node] = []
    dates: list[DateFilter] = []
    for child in node.children:
        new_child, child_dates = _extract_dates(child)
        dates.extend(child_dates)
        if new_child is not None:
            kept.append(new_child)
    return _simplify(type(node), kept), dates


def _flatten_terms(node: Node) -> list[str]:
    """Distinct content terms in tree order."""
    seen: set[str] = set()
    terms: list[str] = []

    def walk(n: Node) -> None:
        if isinstance(n, Field):
            if n.term not in seen:
                seen.add(n.term)
                terms.append(n.term)
        elif isinstance(n, (And, Or)):
            for child in n.children:
                walk(child)

    walk(node)
    return terms


def _resolve_pubyear(dates: list[DateFilter]) -> tuple[int | None, int | None]:
    """Derive inclusive PUBYEAR bounds from raw date clauses."""
    pubyear_from: int | None = None
    pubyear_to: int | None = None
    for d in dates:
        if d.field != "PUBYEAR":
            continue
        if d.op == "AFT":
            pubyear_from = max(pubyear_from, d.value) if pubyear_from is not None else d.value
        elif d.op == "BEF":
            pubyear_to = min(pubyear_to, d.value - 1) if pubyear_to is not None else d.value - 1
        elif d.op == ">":
            lower = d.value + 1
            pubyear_from = max(pubyear_from, lower) if pubyear_from is not None else lower
        elif d.op == "<":
            upper = d.value - 1
            pubyear_to = min(pubyear_to, upper) if pubyear_to is not None else upper
    return pubyear_from, pubyear_to


# Public API ------------------------------------------------------------------


def parse(query: str, term_name: str = "<query>") -> ParsedQuery:
    """Parse a Scopus-subset query into a neutral ``ParsedQuery``.

    Args:
        query: The raw Scopus query string.
        term_name: Human-readable name used in error messages (usually the
            search-term file stem).

    Raises:
        UnsupportedScopusSyntax: If the query uses unsupported operators,
            field names, or structure.
    """
    tokens = _tokenize(query, term_name)
    raw_tree = _Parser(tokens, term_name).parse()
    tree, dates = _extract_dates(raw_tree)
    if tree is None:
        raise UnsupportedScopusSyntax(term_name, "query contains no content terms")
    pubyear_from, pubyear_to = _resolve_pubyear(dates)
    return ParsedQuery(
        tree=tree,
        pubyear_from=pubyear_from,
        pubyear_to=pubyear_to,
        terms=_flatten_terms(tree),
    )
