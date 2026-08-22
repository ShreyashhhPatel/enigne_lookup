"""Tests for the GDELT source adapter.

A fake fetcher returns canned payloads, so these never touch the network. The
fixture mirrors the real DOC 2.0 `artlist` JSON shape.
"""

import json
from datetime import timezone

import pytest

from engine_lookup.sources.base import FetchResult, RateLimited, SourceError
from engine_lookup.sources.gdelt import GdeltSource

# A realistic artlist payload: two good articles + one with no URL (must skip).
_FIXTURE = json.dumps(
    {
        "articles": [
            {
                "url": "https://www.reuters.com/markets/ecb-raises-rates?utm_source=feed",
                "url_mobile": "",
                "title": "ECB raises rates by half a point",
                "seendate": "20260822T120000Z",
                "socialimage": "https://reuters.com/img.jpg",
                "domain": "reuters.com",
                "language": "English",
                "sourcecountry": "United Kingdom",
            },
            {
                "url": "https://apnews.com/article/ecb-rate-decision",
                "title": "ECB lifts rates as inflation persists",
                "seendate": "20260822T130000Z",
                "domain": "apnews.com",
                "language": "English",
                "sourcecountry": "United States",
            },
            {  # no url -> should be skipped, not crash
                "title": "Orphan headline with no link",
                "seendate": "20260822T140000Z",
            },
        ]
    }
)


class FakeFetcher:
    """Records the URLs it was asked for and returns a preset FetchResult."""

    def __init__(self, result: FetchResult) -> None:
        self.result = result
        self.calls: list[str] = []

    def get(self, url: str, *, timeout: float = 30.0) -> FetchResult:
        self.calls.append(url)
        return self.result


def _ok(text: str) -> FetchResult:
    return FetchResult(status=200, text=text, url="https://api.gdeltproject.org/x")


def _source(result: FetchResult) -> tuple[GdeltSource, FakeFetcher]:
    fetcher = FakeFetcher(result)
    # min_interval=0 disables throttling so tests don't wait.
    return GdeltSource(fetcher, min_interval=0), fetcher


# -- URL building ----------------------------------------------------------


def test_build_url_encodes_query_and_sets_mode():
    src, _ = _source(_ok(_FIXTURE))
    url = src.build_url('"Christine Lagarde"', timespan="3d", max_records=10)
    assert "mode=artlist" in url
    assert "format=json" in url
    assert "timespan=3d" in url
    assert "maxrecords=10" in url
    # Quotes and space are percent-encoded, not raw.
    assert "%22Christine+Lagarde%22" in url or "%22Christine%20Lagarde%22" in url


# -- parsing ---------------------------------------------------------------


def test_search_parses_articles_and_skips_urlless_entries():
    src, fetcher = _source(_ok(_FIXTURE))
    docs = src.search('"ECB"')
    assert len(docs) == 2  # the orphan with no URL is skipped
    assert fetcher.calls  # the fetcher was actually invoked


def test_search_maps_fields_correctly():
    src, _ = _source(_ok(_FIXTURE))
    doc = src.search('"ECB"')[0]
    assert doc.source == "gdelt"
    assert doc.domain == "reuters.com"
    assert doc.language == "English"
    assert doc.title == "ECB raises rates by half a point"
    # seendate parsed to an aware UTC datetime.
    assert doc.published_at is not None
    assert doc.published_at.tzinfo == timezone.utc
    assert (doc.published_at.year, doc.published_at.hour) == (2026, 12)
    # canonical_url applied (utm stripped, www dropped).
    assert doc.canonical_url == "https://reuters.com/markets/ecb-raises-rates"
    # extras land in meta.
    assert doc.meta.get("sourcecountry") == "United Kingdom"


# -- error handling --------------------------------------------------------


def test_http_429_raises_rate_limited():
    src, _ = _source(FetchResult(status=429, text="slow down", url="u"))
    with pytest.raises(RateLimited):
        src.search('"ECB"')


def test_plaintext_limit_notice_with_200_raises_rate_limited():
    # GDELT sometimes serves the rate-limit notice as HTTP 200 plaintext.
    notice = "Please limit requests to one every 5 seconds or contact ..."
    src, _ = _source(_ok(notice))
    with pytest.raises(RateLimited):
        src.search('"ECB"')


def test_other_non_json_200_raises_source_error():
    src, _ = _source(_ok("<html>maintenance</html>"))
    with pytest.raises(SourceError):
        src.search('"ECB"')


def test_non_200_status_raises_source_error():
    src, _ = _source(FetchResult(status=503, text="", url="u"))
    with pytest.raises(SourceError):
        src.search('"ECB"')


# -- throttling ------------------------------------------------------------


def test_throttle_waits_between_requests():
    # Fake clock + recording sleep: first call sets the clock, second must wait
    # the remaining interval.
    # monotonic() readings: call 1 reads 100.0 (sets last_request_at); call 2
    # reads 101.0 (1s elapsed -> sleep ~4s), then re-reads 106.0.
    ticks = iter([100.0, 101.0, 106.0])
    slept: list[float] = []
    fetcher = FakeFetcher(_ok(_FIXTURE))
    src = GdeltSource(
        fetcher,
        min_interval=5.0,
        sleep=slept.append,
        monotonic=lambda: next(ticks),
    )
    src.search('"a"')  # reads 100.0 -> last_request_at = 100.0
    src.search('"b"')  # reads 101.0 -> 1s elapsed -> must sleep ~4s
    assert slept and abs(slept[0] - 4.0) < 1e-6


def test_no_throttle_when_interval_zero():
    slept: list[float] = []
    fetcher = FakeFetcher(_ok(_FIXTURE))
    src = GdeltSource(fetcher, min_interval=0, sleep=slept.append)
    src.search('"a"')
    src.search('"b"')
    assert slept == []  # never sleeps when throttling is disabled
