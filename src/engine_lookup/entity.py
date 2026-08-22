"""The entity record — the disambiguation anchor of the whole system.

Everything downstream hangs off this object: dedup groups mentions *about* an
entity, candidate matching fuzzy-matches *against* it, and the LangGraph
investigation loop iteratively *enriches* it. Get this model right and the rest
of the pipeline has a stable spine; get it wrong and every later stage inherits
the ambiguity.

Design notes worth keeping in mind:

* `entity_type` is REQUIRED with no default. That is deliberate — it is the
  legal boundary (public figure vs. private individual, see docs/CONSTRAINTS.md)
  and forcing a choice at construction time means no code path can create a
  target without deciding which side of that line it sits on.

* A profile holds only *confirmed* facts. The two-source attestation rule that
  decides whether a discovered alias/handle is real lives in the graph's
  `update_profile` node, not here. By the time something reaches this object it
  has already earned its place, so `merge()` can trust its input.

* `merge()` returns a NEW profile and never mutates in place. The graph keeps
  the profile in its state and passes it between nodes; in-place mutation there
  is how you get spooky action across iterations. Immutability keeps each
  iteration's view of the profile stable.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    """Which side of the privacy boundary a target sits on.

    Monitoring a public figure's public statements is standard practice.
    Building a dossier on a private individual is a different thing legally
    (PIPEDA / GDPR) and ethically — so the distinction is a first-class,
    required field rather than a comment. See docs/CONSTRAINTS.md.
    """

    PUBLIC_FIGURE = "public_figure"
    PRIVATE_INDIVIDUAL = "private_individual"


def _norm(value: str) -> str:
    """Normalization key used only for de-duplication and comparison.

    Case- and whitespace-insensitive. We keep the original casing in the stored
    value (display matters) and use this collapsed form purely to decide whether
    two strings are "the same".
    """
    return " ".join(value.split()).casefold()


def _dedupe(values: Iterable[str]) -> list[str]:
    """Order-preserving, case-insensitive de-dup of a string collection.

    First spelling wins, so "J. R. Doe" seen before "j. r. doe" keeps the nicer
    casing. Order preservation keeps digests deterministic across runs.
    """
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if not v or not v.strip():
            continue
        key = _norm(v)
        if key not in seen:
            seen.add(key)
            out.append(v.strip())
    return out


class Handle(BaseModel):
    """A social handle, scoped to the platform it lives on.

    Kept as (platform, handle) rather than a bare string because "@jdoe" on
    Bluesky and "@jdoe" on Reddit are different people until proven otherwise.
    """

    platform: str
    handle: str

    def key(self) -> tuple[str, str]:
        """Identity key for de-dup: same platform + same handle."""
        return (_norm(self.platform), _norm(self.handle.lstrip("@")))


class Affiliation(BaseModel):
    """A time-scoped role at an organization (the "TimedRole" from the design).

    Time-scoped because "CTO at Acme" is a strong disambiguation signal *for the
    period it was true* — matching a 2010 article against a 2024 employer is how
    you link the wrong person. `start`/`end` are free-form strings for now
    (often only a year is known); tighten to dates when a source warrants it.
    """

    organization: str
    title: str | None = None
    start: str | None = None
    end: str | None = None

    def key(self) -> tuple[str, str]:
        return (_norm(self.organization), _norm(self.title or ""))


class EntityProfile(BaseModel):
    """The canonical record for one person we are tracking.

    Only `canonical_name` and `entity_type` are required — a profile can start
    as little more than a name and a privacy classification, then enrich itself
    as the investigation loop discovers aliases, handles, and affiliations.
    """

    canonical_name: str
    entity_type: EntityType

    # Wikidata QID (e.g. "Q42") when the target is notable enough to have one.
    # A strong, globally-unique disambiguation anchor when present.
    wikidata_qid: str | None = None

    aliases: list[str] = Field(default_factory=list)
    handles: list[Handle] = Field(default_factory=list)
    affiliations: list[Affiliation] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    # People frequently co-mentioned with the target. Co-occurrence of a known
    # associate in a mention's context is one of the strongest cheap signals
    # that we found the right person (see the entity-linking design).
    known_associates: list[str] = Field(default_factory=list)

    notes: str | None = None

    # ---- Derived views ---------------------------------------------------
    # The entity-linking feature functions want flat sets of employers, roles,
    # and handle strings. Expose them as properties so callers don't have to
    # know the richer internal shape.

    @property
    def employers(self) -> set[str]:
        """Flat set of organization names across all affiliations."""
        return {a.organization for a in self.affiliations if a.organization}

    @property
    def roles(self) -> set[str]:
        """Flat set of role titles across all affiliations."""
        return {a.title for a in self.affiliations if a.title}

    @property
    def handle_values(self) -> set[str]:
        """Flat set of handle strings (without a leading @), across platforms."""
        return {h.handle.lstrip("@") for h in self.handles if h.handle}

    @property
    def match_terms(self) -> set[str]:
        """Everything a high-recall candidate matcher should search for."""
        return {self.canonical_name, *self.aliases}

    # ---- Enrichment ------------------------------------------------------

    def merge(self, updates: Mapping[str, Any]) -> "EntityProfile":
        """Return a NEW profile with `updates` folded in (never mutates self).

        `updates` is a loose mapping — typically the promoted output of the
        graph's profile-extraction step. Keys are forgiving on purpose so the
        caller can speak the design's vocabulary ("employers", "associates") or
        the model's ("affiliations", "known_associates"):

            aliases              -> list[str]
            locations            -> list[str]
            associates           -> list[str]   (alias for known_associates)
            known_associates     -> list[str]
            handles              -> dict[platform, handle] | list[Handle | dict]
            employers            -> list[Affiliation | dict]  (alias for below)
            affiliations         -> list[Affiliation | dict]
            wikidata_qid         -> str
            notes                -> str

        Unknown keys are ignored rather than raising, so an over-eager extractor
        can't crash enrichment.
        """
        merged: dict[str, Any] = self.model_dump()

        # Simple string collections: union + de-dup, existing values first.
        merged["aliases"] = _dedupe([*self.aliases, *updates.get("aliases", [])])
        merged["locations"] = _dedupe([*self.locations, *updates.get("locations", [])])
        merged["known_associates"] = _dedupe(
            [
                *self.known_associates,
                *updates.get("known_associates", []),
                *updates.get("associates", []),  # design-vocabulary alias
            ]
        )

        # Handles: accept a {platform: handle} dict or a list of Handle/dicts.
        incoming_handles = _coerce_handles(updates.get("handles", []))
        merged["handles"] = _dedupe_models([*self.handles, *incoming_handles])

        # Affiliations: "employers" and "affiliations" mean the same thing here.
        incoming_affs = _coerce_affiliations(
            [*updates.get("affiliations", []), *updates.get("employers", [])]
        )
        merged["affiliations"] = _dedupe_models([*self.affiliations, *incoming_affs])

        # Scalars: only overwrite when the update actually provides a value, so
        # enrichment never blanks out a field we already knew.
        for scalar in ("wikidata_qid", "notes"):
            if updates.get(scalar):
                merged[scalar] = updates[scalar]

        return EntityProfile.model_validate(merged)


def _coerce_handles(raw: Any) -> list[Handle]:
    """Turn the several shapes a caller might pass into a list of Handle."""
    if isinstance(raw, Mapping):
        # {platform: handle} shorthand from the extraction schema.
        return [Handle(platform=p, handle=h) for p, h in raw.items()]
    out: list[Handle] = []
    for item in raw or []:
        out.append(item if isinstance(item, Handle) else Handle.model_validate(item))
    return out


def _coerce_affiliations(raw: Iterable[Any]) -> list[Affiliation]:
    out: list[Affiliation] = []
    for item in raw or []:
        if isinstance(item, Affiliation):
            out.append(item)
        elif isinstance(item, str):
            # A bare org name with no title/dates is still useful.
            out.append(Affiliation(organization=item))
        else:
            out.append(Affiliation.model_validate(item))
    return out


def _dedupe_models(models: list[Any]) -> list[dict[str, Any]]:
    """De-dup Handle/Affiliation by their `key()`, first occurrence wins.

    Returns dicts (not model instances) because the result feeds straight back
    into `model_validate` on the parent profile.
    """
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for m in models:
        if m.key() not in seen:
            seen.add(m.key())
            out.append(m.model_dump())
    return out
