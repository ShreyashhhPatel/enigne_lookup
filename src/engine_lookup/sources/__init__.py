"""Source adapters — the breadth layer's ingestion edge.

Each source turns an external API into a list of normalized `Document`s. The
HTTP seam (`Fetcher`) is injectable so the parsing logic is testable without a
network, and so a source can be pointed at a polite/cached/mock transport.

All of this is plain functions and classes the pipeline calls — none of it
belongs in the LangGraph graph (see docs/CONSTRAINTS.md).
"""

from engine_lookup.sources.base import (
    DEFAULT_USER_AGENT,
    FetchResult,
    Fetcher,
    RateLimited,
    SourceError,
    UrllibFetcher,
)
from engine_lookup.sources.gdelt import GdeltSource

__all__ = [
    "DEFAULT_USER_AGENT",
    "FetchResult",
    "Fetcher",
    "GdeltSource",
    "RateLimited",
    "SourceError",
    "UrllibFetcher",
]
