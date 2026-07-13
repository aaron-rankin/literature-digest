"""Translate parsed Scopus-subset queries into per-source request params.

Two date axes are kept strictly separate:

* Crawl window (``last_run - lookback -> now``) maps to each source's
  *indexed/created* date filter. On the first run the window is capped to a
  configured number of days (default 90) rather than being unbounded.
* Publication recency (``PUBYEAR`` clauses in the authored ``.txt`` file) maps
  to each source's *publication* date filter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from literature_digest.query.scopus_parser import And, Field, Node, Or, ParsedQuery


@dataclass
class DateWindow:
    """The two date axes for one source query."""

    crawl_from: datetime | None = None  # inclusive lower bound for indexed/created date
    crawl_to: datetime | None = None  # inclusive upper bound for indexed/created date
    pub_from: datetime | None = None  # inclusive lower bound for publication date
    pub_to: datetime | None = None  # inclusive upper bound for publication date


@dataclass
class SourceQuery:
    """A single search term ready to be sent to a source."""

    term_name: str
    parsed: ParsedQuery
    area_slug: str = ""


class QueryTranslator:
    """Convert a ``SourceQuery`` + ``DateWindow`` into source-specific params."""

    # --------------------------------------------------------------------- #
    # Scopus
    # --------------------------------------------------------------------- #
    def to_scopus(self, q: SourceQuery, window: DateWindow) -> str:
        """Render a Scopus Search API query string.

        The authored boolean tree is round-tripped to Scopus DSL, then the
        pipeline-owned crawl window and canonical PUBYEAR bounds are appended.
        ``ORIG-LOAD-DATE`` uses ``YYYYMMDD``; ``PUBYEAR AFT`` is inclusive.
        """
        parts: list[str] = [self._scopus_node(q.parsed.tree)]

        if window.crawl_from is not None:
            parts.append(f"ORIG-LOAD-DATE AFT {self._fmt_scopus_date(window.crawl_from)}")
        if window.crawl_to is not None:
            parts.append(f"ORIG-LOAD-DATE BEF {self._fmt_scopus_date(window.crawl_to)}")

        if q.parsed.pubyear_from is not None:
            parts.append(f"PUBYEAR AFT {q.parsed.pubyear_from}")
        if q.parsed.pubyear_to is not None:
            parts.append(f"PUBYEAR < {q.parsed.pubyear_to + 1}")

        return " AND ".join(parts)

    @staticmethod
    def _scopus_node(node: Node) -> str:
        if isinstance(node, Field):
            return f"{node.op}({node.term})"
        if isinstance(node, And):
            inner = " AND ".join(QueryTranslator._scopus_node(c) for c in node.children)
            return f"({inner})"
        if isinstance(node, Or):
            inner = " OR ".join(QueryTranslator._scopus_node(c) for c in node.children)
            return f"({inner})"
        # DateFilter nodes are stripped during parsing and handled separately.
        raise TypeError(f"unexpected node type: {type(node).__name__}")

    @staticmethod
    def _fmt_scopus_date(dt: datetime) -> str:
        return dt.astimezone(UTC).strftime("%Y%m%d")

    # --------------------------------------------------------------------- #
    # OpenAlex
    # --------------------------------------------------------------------- #
    def to_openalex(self, q: SourceQuery, window: DateWindow) -> dict[str, Any]:
        """Return OpenAlex ``works`` search params.

        The boolean tree is rendered as faithfully as possible (quoted phrases,
        AND/OR, parentheses). Field operators collapse to plain full-text
        search. Filters keep the crawl window on ``from_created_date`` and the
        publication recency on ``from_publication_date`` / ``to_publication_date``.
        """
        params: dict[str, Any] = {
            "search": self._openalex_node(q.parsed.tree),
            "per-page": 100,
            "cursor": "*",
        }

        filters: list[str] = []
        if window.crawl_from is not None:
            filters.append(f"from_created_date:{self._fmt_iso_date(window.crawl_from)}")
        if window.crawl_to is not None:
            filters.append(f"to_created_date:{self._fmt_iso_date(window.crawl_to)}")
        if window.pub_from is not None:
            filters.append(f"from_publication_date:{self._fmt_iso_date(window.pub_from)}")
        if window.pub_to is not None:
            filters.append(f"to_publication_date:{self._fmt_iso_date(window.pub_to)}")

        if filters:
            params["filter"] = ",".join(filters)
        return params

    @staticmethod
    def _openalex_node(node: Node) -> str:
        if isinstance(node, Field):
            return QueryTranslator._quote_phrase(node.term)
        if isinstance(node, And):
            inner = " AND ".join(QueryTranslator._openalex_node(c) for c in node.children)
            return f"({inner})"
        if isinstance(node, Or):
            inner = " OR ".join(QueryTranslator._openalex_node(c) for c in node.children)
            return f"({inner})"
        raise TypeError(f"unexpected node type: {type(node).__name__}")

    @staticmethod
    def _quote_phrase(text: str) -> str:
        """Quote a multi-word term unless the user already quoted it."""
        text = text.strip()
        if text.startswith('"') and text.endswith('"'):
            return text
        if " " in text:
            return f'"{text}"'
        return text

    # --------------------------------------------------------------------- #
    # Crossref
    # --------------------------------------------------------------------- #
    def to_crossref(self, q: SourceQuery, window: DateWindow) -> dict[str, Any]:
        """Return Crossref ``works`` search params.

        Crossref has no real boolean query syntax, so we free-text the content
        terms and rely on date filters plus downstream screening. The crawl
        window maps to ``from-index-date`` / ``until-index-date`` and PUBYEAR
        maps to ``from-pub-date`` / ``until-pub-date``.
        """
        stripped_terms = [t.strip("\"'") for t in q.parsed.terms]
        params: dict[str, Any] = {
            "query": " ".join(stripped_terms),
            "rows": 100,
            "cursor": "*",
        }

        filters: list[str] = []
        if window.crawl_from is not None:
            filters.append(f"from-index-date:{self._fmt_iso_date(window.crawl_from)}")
        if window.crawl_to is not None:
            filters.append(f"until-index-date:{self._fmt_iso_date(window.crawl_to)}")
        if window.pub_from is not None:
            filters.append(f"from-pub-date:{self._fmt_iso_date(window.pub_from)}")
        if window.pub_to is not None:
            filters.append(f"until-pub-date:{self._fmt_iso_date(window.pub_to)}")

        if filters:
            params["filter"] = ",".join(filters)
        return params

    @staticmethod
    def _fmt_iso_date(dt: datetime) -> str:
        return dt.astimezone(UTC).date().isoformat()


# ----------------------------------------------------------------------------- #
# Window computation
# ----------------------------------------------------------------------------- #


def compute_date_window(
    last_run: datetime | None,
    lookback_days: int,
    first_run_lookback_days: int,
    pubyear_from: int | None,
    pubyear_to: int | None,
    now: datetime | None = None,
) -> DateWindow:
    """Build a ``DateWindow`` from pipeline state and a parsed query."""
    now = now or datetime.now(UTC)

    if last_run is None:
        crawl_from = now - timedelta(days=first_run_lookback_days)
    else:
        crawl_from = last_run - timedelta(days=lookback_days)

    pub_from = datetime(pubyear_from, 1, 1, tzinfo=UTC) if pubyear_from else None
    pub_to = datetime(pubyear_to, 12, 31, tzinfo=UTC) if pubyear_to else None

    return DateWindow(
        crawl_from=crawl_from,
        crawl_to=now,
        pub_from=pub_from,
        pub_to=pub_to,
    )
