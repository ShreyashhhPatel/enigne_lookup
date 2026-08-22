"""The Document model — one fetched item (news article, post) before linking.

A Document is the normalized unit every source poller emits and everything
downstream consumes: dedup fingerprints its `dedup_text`, candidate matching
scans its `title`/`text`, and entity linking reads its context window. Sources
differ wildly (a GDELT article vs. a Bluesky post), so this model is the common
shape they all flatten into.

Deliberately NOT the entity — a Document is *a mention*, not *a person*. It may
be about our target, someone else, or nobody we track; deciding that is the
linking layer's job later.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from engine_lookup.dedup import canonicalize_url


class Document(BaseModel):
    """A single fetched item, normalized across sources."""

    source: str  # which poller produced this ("gdelt", "bluesky", ...)
    source_id: str  # stable id within that source (often the URL or post URI)
    url: str

    # Computed dedup key (see dedup.canonicalize_url). Filled automatically from
    # `url` when not supplied; kept as a separate field so the raw `url` stays
    # intact for fetching (the canonical form forces https / strips www and is
    # a comparison key, not a guaranteed-fetchable link).
    canonical_url: str = ""

    title: str = ""
    # Article/post body. Often EMPTY on first ingest — e.g. GDELT returns
    # metadata only; the body arrives from a later fetch+extract step.
    text: str = ""

    published_at: datetime | None = None
    authors: list[str] = Field(default_factory=list)
    language: str | None = None
    domain: str | None = None

    # Source-specific extras we don't want to model as first-class fields yet
    # (sourcecountry, social image, post metrics, ...).
    meta: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _fill_canonical_url(self) -> "Document":
        if not self.canonical_url and self.url:
            self.canonical_url = canonicalize_url(self.url)
        return self

    @property
    def dedup_text(self) -> str:
        """The text SimHash should fingerprint: full body if we have it, else
        the title. Titles alone are a weak signal, but better than nothing until
        the body-extraction step lands."""
        return self.text.strip() or self.title.strip()
