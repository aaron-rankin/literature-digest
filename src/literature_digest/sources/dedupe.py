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

Articles without a DOI are kept as-is (treated as unique). The merged Article
inherits `area_slug` from the first member of its group.

Phase 2 will implement the merge logic; for now returns the input unchanged.
"""

from __future__ import annotations

from literature_digest.models import Article

# Source precedence: first non-null wins for each field
SOURCE_PRECEDENCE = ("scopus_api", "openalex", "crossref", "scopus_email")


class Deduper:
    """Merges a list of Articles by normalized DOI. Placeholder body."""

    def dedupe(self, articles: list[Article]) -> list[Article]:
        """Dedupe and merge `articles` by DOI.

        PLACEHOLDER: returns the input list unchanged. Phase 2 will implement
        DOI normalization + field-level merge with source precedence.
        """
        # TODO(phase-2): normalize DOIs, group, merge by precedence
        return list(articles)
