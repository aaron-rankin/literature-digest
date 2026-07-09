# Subtask 02 — Scopus-subset query parser

**To-do:** Paper Finding → enables cross-source querying
**Decisions:** D3, D4
**Depends on:** nothing (pure module, unit-testable)

## Goal

Parse the narrow Scopus-DSL subset used in the `.txt` files into a neutral term
tree, separating content terms from date filters, and **reject** anything
outside the supported grammar.

## Supported grammar (from the four existing files)

- Field ops: `TITLE-ABS-KEY ( <term> )`, `TITLE-ABS-KEY-AUTH ( <term> )`.
  `<term>` is free text (may be multi-word, unquoted), optionally quoted.
- Boolean: `AND`, `OR`, with parentheses for grouping/nesting.
- Date filters (parsed out separately, not part of the term tree):
  - `PUBYEAR > N`, `PUBYEAR < N`, `PUBYEAR AFT N` → publication-year bounds.
  - `ORIG-LOAD-DATE AFT <epoch>`, `ORIG-LOAD-DATE BEF <epoch>` → **discarded**
    (pipeline owns the crawl window, D4).

> ⚠️ **Operator precedence — keep Scopus-native (DECIDED).** Scopus evaluates
> `OR` before `AND` (differs from most languages). `a AND b OR c` =
> `a AND (b OR c)`. The parser mirrors Scopus exactly so our translation matches
> Scopus's own result set. Encode this and cover it with an explicit test —
> getting it wrong silently changes result sets.

## Neutral representation

```python
# term tree nodes
Field(op: Literal["TITLE-ABS-KEY","TITLE-ABS-KEY-AUTH"], term: str)
And(children: list[Node])
Or(children: list[Node])

@dataclass
class ParsedQuery:
    tree: Node
    pubyear_from: int | None   # inclusive lower bound derived from > / AFT
    pubyear_to: int | None     # inclusive upper bound derived from <
    terms: list[str]           # flattened distinct content terms (for logging / crude fallback)
```

- **`AFT` is inclusive (DECIDED).** `PUBYEAR AFT 2024` → `pubyear_from = 2024`.
  `>` is strictly-after: `PUBYEAR > 2023` → `pubyear_from = 2024`. `<` is
  strictly-before: `PUBYEAR < 2027` → `pubyear_to = 2026`. When multiple
  PUBYEAR clauses appear, take the tightest bound (max of lowers, min of uppers).

## Implementation steps

1. New module `src/literature_digest/query/scopus_parser.py`.
2. Tokenizer → recursive-descent parser (or a small pratt parser) honoring the
   `OR`-before-`AND` precedence.
3. Strip/extract date clauses before/while building the tree so they don't leak
   into `Field` nodes.
4. On any unsupported token/field op, raise `UnsupportedScopusSyntax(term_name,
   detail)` — the loader surfaces it as a skipped term with a clear warning.

## Files touched
New `src/literature_digest/query/__init__.py`,
`src/literature_digest/query/scopus_parser.py`; new tests.

## Acceptance criteria
- Parses all four current `.txt` files without error.
- `game_model.txt` → tree `AND[TAK(game model), OR[TAK(football), TAK(soccer)]]`;
  `PUBYEAR > 2023` (→2024) and `PUBYEAR AFT 2024` (→2024) give
  `pubyear_from=2024`, `pubyear_to=2026`; `ORIG-LOAD-DATE` discarded.
- `spatiotemporal.txt` (no dates) → tree only, `pubyear_from/to = None`.
- A query using an unsupported field op (e.g. `AUTHKEY(...)`) raises
  `UnsupportedScopusSyntax`.
- Explicit precedence test: `TAK(a) AND TAK(b) OR TAK(c)` parses as
  `AND[a, OR[b, c]]`.
