"""The HTTP seam shared by source adapters.

`Fetcher` is a tiny protocol (one method: `get`) so sources depend on an
abstraction, not on urllib. The default `UrllibFetcher` uses the standard
library only — no third-party HTTP dependency for a handful of GETs. Tests inject
a fake fetcher returning canned payloads, so no source test ever hits the wire.

Note `UrllibFetcher.get` returns the status on an HTTP error rather than
raising: sources need to see a 429 to back off, so surfacing it as data (not an
exception) keeps that decision in the source where it belongs.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

DEFAULT_USER_AGENT = (
    "engine_lookup/0.0 (+https://github.com/ShreyashhhPatel/enigne_lookup)"
)


class FetchResult(BaseModel):
    """The outcome of one HTTP GET."""

    status: int
    text: str
    url: str  # final URL after redirects, when the transport reports it


@runtime_checkable
class Fetcher(Protocol):
    """Anything that can perform an HTTP GET and return a FetchResult."""

    def get(self, url: str, *, timeout: float = 30.0) -> FetchResult: ...


class UrllibFetcher:
    """Default `Fetcher` backed by the standard library."""

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self._user_agent = user_agent

    def get(self, url: str, *, timeout: float = 30.0) -> FetchResult:
        request = urllib.request.Request(url, headers={"User-Agent": self._user_agent})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", "replace")
                return FetchResult(status=response.status, text=body, url=response.url)
        except urllib.error.HTTPError as exc:
            # Return the error status as data (e.g. 429) so the caller can back
            # off; read the body when present for a useful error message.
            body = exc.read().decode("utf-8", "replace") if exc.fp else ""
            return FetchResult(status=exc.code, text=body, url=url)


class SourceError(Exception):
    """A source failed to produce results (bad status, unparseable payload)."""


class RateLimited(SourceError):
    """The source rejected us for rate-limiting; back off and retry later."""
