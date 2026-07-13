"""Deduplication and metadata merging across ingestion sources.

Contract:
    dedupe(articles: list[Article]) -> list[Article]

A pure function (no network, no I/O) that:
1. Normalizes DOIs to lowercase, no URL prefix, no trailing punctuation
2. Groups articles by normalized DOI
3. Merges each group into one Article, applying source precedence:
       scopus_api > openalex > crossref > scopus_email
   (first non-null wins for each field)
4. Combines `sources` lists into a single provenance list

Articles without a DOI are kept as-is (treated as unique). Output preserves the
first-appearance order of each DOI group / DOI-less article.
"""

from __future__ import annotations

import re

from literature_digest.models import Article

# Source precedence: first non-null wins for each field.
SOURCE_PRECEDENCE = ("scopus", "openalex", "crossref", "scopus_email", "fixture")

# URL / scheme prefixes that may wrap a DOI.
_DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
)

# Fields merged by source precedence (identity/metadata only; LLM-stage fields
# stay untouched since dedupe runs before screening).
_MERGE_FIELDS = ("title", "abstract", "authors", "journal", "year", "url", "pub_date", "area_slug")


def normalize_doi(raw: str | None) -> str | None:
    """Lowercase a DOI and strip URL prefixes + trailing punctuation.

    Returns None for empty/whitespace-only input. Shared by ingestion sources so
    the DOI stored on every Article is already in canonical form.
    """
    if not raw:
        return None
    doi = raw.strip().lower()
    for prefix in _DOI_PREFIXES:
        if doi.startswith(prefix):
            doi = doi[len(prefix) :]
            break
    # Strip trailing punctuation/brackets sometimes glued on by email/HTML sources.
    doi = re.sub(r"[.,;)\]\s]+$", "", doi.strip())
    return doi or None


class Deduper:
    """Merges a list of Articles by normalized DOI, applying source precedence."""

    def dedupe(self, articles: list[Article]) -> list[Article]:
        """Dedupe and merge `articles` by normalized DOI.

        DOI-less articles pass through unchanged (each is treated as unique).
        DOI-bearing articles are grouped and merged, with output order following
        each DOI's first appearance in the input.
        """
        groups: dict[str, list[Article]] = {}
        # Slots preserve output order: a normalized-DOI key marks a group's first
        # appearance; a bare Article is a DOI-less passthrough.
        slots: list[str | Article] = []

        for art in articles:
            ndoi = normalize_doi(art.doi)
            if ndoi is None:
                art.doi = None
                slots.append(art)
                continue
            if ndoi not in groups:
                groups[ndoi] = []
                slots.append(ndoi)
            groups[ndoi].append(art)

        out: list[Article] = []
        for slot in slots:
            if isinstance(slot, str):
                out.append(self._merge(slot, groups[slot]))
            else:
                out.append(slot)
        return out

    def _merge(self, ndoi: str, members: list[Article]) -> Article:
        """Merge a group of same-DOI articles into one, by source precedence."""
        # Stable sort keeps input order among members of equal precedence.
        ranked = sorted(members, key=self._rank)

        merged = Article(doi=ndoi)
        for field in _MERGE_FIELDS:
            value = self._first(ranked, field)
            if value is not None:
                setattr(merged, field, value)

        # Combine provenance and matched terms in precedence order, de-duplicated.
        seen_sources: list[str] = []
        seen_terms: list[str] = []
        for m in ranked:
            for src in m.sources:
                if src not in seen_sources:
                    seen_sources.append(src)
            for term in m.matched_terms:
                if term not in seen_terms:
                    seen_terms.append(term)
        merged.sources = seen_sources
        merged.matched_terms = seen_terms
        return merged

    @staticmethod
    def _rank(art: Article) -> int:
        """Best (lowest) source-precedence rank for an article; unknown sorts last."""
        ranks = [SOURCE_PRECEDENCE.index(s) for s in art.sources if s in SOURCE_PRECEDENCE]
        return min(ranks) if ranks else len(SOURCE_PRECEDENCE)

    @staticmethod
    def _first(ranked: list[Article], field: str) -> object | None:
        """First truthy value for `field` across precedence-ranked members."""
        for m in ranked:
            value = getattr(m, field)
            if value:  # None, "", [] and 0 all count as "missing"
                return value
        return None
