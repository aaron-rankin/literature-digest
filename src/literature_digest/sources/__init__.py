"""Source package — ingestion clients for Scopus email, Scopus API, and free APIs."""

from literature_digest.sources.crossref import CrossrefSource
from literature_digest.sources.dedupe import Deduper
from literature_digest.sources.local import LocalSource
from literature_digest.sources.openalex import OpenAlexSource
from literature_digest.sources.scopus_api import ScopusApiSource
from literature_digest.sources.scopus_email import ScopusEmailSource

__all__ = [
    "CrossrefSource",
    "Deduper",
    "LocalSource",
    "OpenAlexSource",
    "ScopusApiSource",
    "ScopusEmailSource",
]
