"""Unit tests for the Scopus-subset query parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from literature_digest.query import And, Field, Or, UnsupportedScopusSyntax, parse


def _field(term: str, auth: bool = False) -> Field:
    op = "TITLE-ABS-KEY-AUTH" if auth else "TITLE-ABS-KEY"
    return Field(op, term)


def test_parse_simple_title_abs_key() -> None:
    pq = parse("TITLE-ABS-KEY ( game model )", "game_model")
    assert pq.tree == _field("game model")
    assert pq.pubyear_from is None
    assert pq.pubyear_to is None
    assert pq.terms == ["game model"]


def test_parse_title_abs_key_auth() -> None:
    pq = parse("TITLE-ABS-KEY-AUTH ( spatiotemporal )", "spatiotemporal")
    assert pq.tree == _field("spatiotemporal", auth=True)


def test_parse_or_before_and_precedence() -> None:
    pq = parse(
        "TITLE-ABS-KEY(a) AND TITLE-ABS-KEY(b) OR TITLE-ABS-KEY(c)",
        "precedence",
    )
    assert isinstance(pq.tree, And)
    assert pq.tree.children[0] == _field("a")
    assert isinstance(pq.tree.children[1], Or)
    assert pq.tree.children[1].children == [_field("b"), _field("c")]


def test_parse_parentheses_override_precedence() -> None:
    pq = parse(
        "( TITLE-ABS-KEY(a) AND TITLE-ABS-KEY(b) ) OR TITLE-ABS-KEY(c)",
        "parens",
    )
    assert isinstance(pq.tree, Or)
    assert isinstance(pq.tree.children[0], And)
    assert pq.tree.children[1] == _field("c")


def test_parse_multiword_unquoted_term() -> None:
    pq = parse("TITLE-ABS-KEY ( style of play )", "style_of_play")
    assert pq.tree == _field("style of play")


def test_parse_quoted_term() -> None:
    pq = parse('TITLE-ABS-KEY ( "virtual reality" )', "vr")
    assert pq.tree == _field('"virtual reality"')


def test_parse_game_model_file() -> None:
    text = Path("data/search_terms/data_science/game_model.txt").read_text(encoding="utf-8")
    pq = parse(text, "game_model")
    assert isinstance(pq.tree, And)
    assert pq.tree.children[0] == _field("game model")
    assert isinstance(pq.tree.children[1], Or)
    assert pq.tree.children[1].children == [_field("football"), _field("soccer")]
    assert pq.pubyear_from == 2024
    assert pq.pubyear_to == 2026
    assert pq.terms == ["game model", "football", "soccer"]


def test_parse_spatiotemporal_file_no_dates() -> None:
    text = Path("data/search_terms/data_science/spatiotemporal.txt").read_text(encoding="utf-8")
    pq = parse(text, "spatiotemporal")
    assert isinstance(pq.tree, And)
    assert pq.tree.children[0] == _field("spatiotemporal", auth=True)
    assert isinstance(pq.tree.children[1], Or)
    assert pq.tree.children[1].children == [
        _field("football", auth=True),
        _field("soccer", auth=True),
    ]
    assert pq.pubyear_from is None
    assert pq.pubyear_to is None


def test_parse_pubyear_bounds() -> None:
    pq = parse(
        "TITLE-ABS-KEY(x) AND PUBYEAR > 2023 AND PUBYEAR < 2027 AND PUBYEAR AFT 2024",
        "bounds",
    )
    assert pq.pubyear_from == 2024
    assert pq.pubyear_to == 2026


def test_parse_orig_load_date_is_discarded() -> None:
    pq = parse(
        "TITLE-ABS-KEY(x) AND ORIG-LOAD-DATE AFT 1779408000 AND ORIG-LOAD-DATE BEF 1780012800",
        "load_date",
    )
    assert pq.pubyear_from is None
    assert pq.pubyear_to is None


def test_parse_tightest_bound_wins() -> None:
    query = (
        "TITLE-ABS-KEY(x) AND PUBYEAR > 2020 AND PUBYEAR AFT 2024 "
        "AND PUBYEAR < 2030 AND PUBYEAR BEF 2026"
    )
    pq = parse(query, "tightest")
    assert pq.pubyear_from == 2024
    assert pq.pubyear_to == 2025


def test_parse_unsupported_field_op_raises() -> None:
    with pytest.raises(UnsupportedScopusSyntax) as exc_info:
        parse("AUTHKEY(athlete)", "bad")
    assert "unsupported field" in str(exc_info.value).lower()


def test_parse_unsupported_date_op_raises() -> None:
    with pytest.raises(UnsupportedScopusSyntax):
        parse("TITLE-ABS-KEY(x) AND PUBYEAR = 2024", "bad_date_op")


def test_parse_empty_term_raises() -> None:
    with pytest.raises(UnsupportedScopusSyntax):
        parse("TITLE-ABS-KEY()", "empty")


def test_parse_unexpected_trailing_tokens_raises() -> None:
    with pytest.raises(UnsupportedScopusSyntax):
        parse("TITLE-ABS-KEY(x) EXTRA", "trailing")


def test_parse_empty_query_raises() -> None:
    with pytest.raises(UnsupportedScopusSyntax):
        parse("   ", "empty")


def test_parse_repr_uses_shorthand() -> None:
    pq = parse("TITLE-ABS-KEY ( foo )", "foo")
    assert repr(pq.tree) == "TAK(foo)"

    pq = parse("TITLE-ABS-KEY-AUTH ( bar )", "bar")
    assert repr(pq.tree) == "TAK-AUTH(bar)"


def test_parse_and_or_repr() -> None:
    pq = parse("TITLE-ABS-KEY(a) AND TITLE-ABS-KEY(b) OR TITLE-ABS-KEY(c)", "repr")
    assert repr(pq.tree) == "AND[TAK(a), OR[TAK(b), TAK(c)]]"
