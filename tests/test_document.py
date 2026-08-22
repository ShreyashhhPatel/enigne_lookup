"""Tests for the Document model."""

from datetime import datetime, timezone

from engine_lookup.document import Document


def test_canonical_url_is_computed_from_url():
    d = Document(
        source="gdelt",
        source_id="x",
        url="https://www.example.com/story?utm_source=x&id=7",
    )
    # Tracking param stripped, www dropped, scheme normalized — the dedup key.
    assert d.canonical_url == "https://example.com/story?id=7"


def test_explicit_canonical_url_is_respected():
    d = Document(
        source="gdelt",
        source_id="x",
        url="https://example.com/a",
        canonical_url="https://example.com/override",
    )
    assert d.canonical_url == "https://example.com/override"


def test_dedup_text_prefers_body_then_falls_back_to_title():
    with_body = Document(source="s", source_id="1", url="u", title="Head", text="Body here")
    assert with_body.dedup_text == "Body here"

    title_only = Document(source="s", source_id="2", url="u", title="Just a headline")
    assert title_only.dedup_text == "Just a headline"


def test_published_at_is_optional():
    d = Document(source="s", source_id="1", url="u")
    assert d.published_at is None

    dt = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
    d2 = Document(source="s", source_id="1", url="u", published_at=dt)
    assert d2.published_at == dt
