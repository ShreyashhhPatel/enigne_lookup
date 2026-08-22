"""GDELT DOC 2.0 source adapter — the news backbone.

GDELT monitors global news media and is free with no key. We use the `artlist`
mode of the DOC 2.0 API, which returns article METADATA (url, title, seendate,
domain, language) — importantly NOT the article body. Body text comes from a
later fetch+extract step; until then a Document's `dedup_text` falls back to its
title.

Two operational facts learned the hard way and baked in here:

* GDELT asks for **at most one request every 5 seconds**. `GdeltSource`
  self-throttles to honour that.
* Over-limit or malformed queries can come back as HTTP 429, or as an HTTP 200
  with a plaintext (non-JSON) error body. Both are detected and surfaced as
  `RateLimited` / `SourceError` rather than crashing the parser.
"""

from __future__ import annotations

import json
import time
import urllib.parse
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from engine_lookup.document import Document
from engine_lookup.sources.base import (
    Fetcher,
    RateLimited,
    SourceError,
    UrllibFetcher,
)

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"


class GdeltSource:
    """Search GDELT for articles and return normalized `Document`s.

    The fetcher, sleep, and clock are injectable so the throttle and parsing are
    fully testable without a network or real wall-clock waits.
    """

    name = "gdelt"

    def __init__(
        self,
        fetcher: Fetcher | None = None,
        *,
        min_interval: float = 5.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetcher = fetcher or UrllibFetcher()
        self._min_interval = min_interval
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request_at: float | None = None

    # -- request building --------------------------------------------------

    def build_url(
        self,
        query: str,
        *,
        timespan: str = "1d",
        max_records: int = 75,
        sort: str = "datedesc",
    ) -> str:
        """Build the DOC 2.0 artlist URL.

        `query` is passed through verbatim so callers can use GDELT operators
        (exact phrases in quotes, `domain:`, boolean, etc.). urlencode handles
        the quoting.
        """
        params = {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": str(max_records),
            "timespan": timespan,
            "sort": sort,
        }
        return f"{GDELT_DOC_API}?{urllib.parse.urlencode(params)}"

    # -- search ------------------------------------------------------------

    def search(self, query: str, **kwargs: Any) -> list[Document]:
        """Run one search and return the parsed Documents (skips junk entries)."""
        self._throttle()
        result = self._fetcher.get(self.build_url(query, **kwargs))

        if result.status == 429 or _looks_rate_limited(result.text):
            raise RateLimited("GDELT rate limit (max one request every 5 seconds)")
        if result.status != 200:
            raise SourceError(f"GDELT returned HTTP {result.status}")

        try:
            payload = json.loads(result.text)
        except json.JSONDecodeError as exc:
            # A 200 with a non-JSON body is GDELT signalling an error in text.
            raise SourceError(f"GDELT non-JSON response: {result.text[:200]!r}") from exc

        documents: list[Document] = []
        for article in payload.get("articles", []):
            document = self._to_document(article)
            if document is not None:
                documents.append(document)
        return documents

    # -- internals ---------------------------------------------------------

    def _throttle(self) -> None:
        """Sleep just enough to keep to one request per `min_interval` seconds."""
        now = self._monotonic()
        if self._min_interval > 0 and self._last_request_at is not None:
            wait = self._min_interval - (now - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
                now = self._monotonic()
        self._last_request_at = now

    def _to_document(self, article: dict[str, Any]) -> Document | None:
        url = article.get("url")
        if not url:
            return None  # an entry with no URL is unusable; skip it.
        return Document(
            source=self.name,
            source_id=url,
            url=url,
            title=article.get("title") or "",
            published_at=_parse_seendate(article.get("seendate")),
            language=article.get("language") or None,
            domain=article.get("domain") or None,
            meta={
                key: article[key]
                for key in ("sourcecountry", "socialimage", "url_mobile")
                if article.get(key)
            },
        )


def _parse_seendate(value: str | None) -> datetime | None:
    """Parse GDELT's `YYYYMMDDTHHMMSSZ` timestamp into an aware UTC datetime."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _looks_rate_limited(text: str) -> bool:
    """Detect GDELT's plaintext rate-limit notice (sometimes served with 200)."""
    return "limit requests" in text.lower()
