"""Tests for the EntityProfile model.

These double as the executable half of the design's guarantees: entity_type is
mandatory (the privacy guardrail), and merge() is a pure, de-duplicating union.
"""

import pytest
from pydantic import ValidationError

from engine_lookup import Affiliation, EntityProfile, EntityType, Handle


def _jane() -> EntityProfile:
    return EntityProfile(
        canonical_name="Jane Doe",
        entity_type=EntityType.PUBLIC_FIGURE,
        affiliations=[Affiliation(organization="Acme", title="CTO")],
        handles=[Handle(platform="bluesky", handle="@jdoe")],
        aliases=["Jane R. Doe"],
    )


def test_entity_type_is_required():
    # The privacy classification has no default: you cannot create a target
    # without deciding whether it is a public figure or a private individual.
    with pytest.raises(ValidationError):
        EntityProfile(canonical_name="Jane Doe")  # type: ignore[call-arg]


def test_minimal_profile_construction():
    p = EntityProfile(canonical_name="Jane Doe", entity_type=EntityType.PUBLIC_FIGURE)
    assert p.canonical_name == "Jane Doe"
    assert p.entity_type is EntityType.PUBLIC_FIGURE
    assert p.aliases == []
    assert p.employers == set()


def test_derived_views():
    p = _jane()
    assert p.employers == {"Acme"}
    assert p.roles == {"CTO"}
    assert p.handle_values == {"jdoe"}  # leading @ stripped
    assert p.match_terms == {"Jane Doe", "Jane R. Doe"}


def test_merge_is_pure_and_returns_new_object():
    p = _jane()
    p2 = p.merge({"aliases": ["J. R. Doe"]})
    assert p2 is not p
    # Original is untouched — no in-place mutation.
    assert p.aliases == ["Jane R. Doe"]
    assert "J. R. Doe" in p2.aliases


def test_merge_dedupes_case_insensitively_keeping_first_spelling():
    p = _jane()
    p2 = p.merge({"aliases": ["jane r. doe", "J. R. Doe"]})
    # "jane r. doe" is a case-dup of the existing "Jane R. Doe" -> dropped,
    # original spelling preserved; only the genuinely new alias is added.
    assert p2.aliases == ["Jane R. Doe", "J. R. Doe"]


def test_merge_accepts_design_vocabulary_aliases():
    # The graph's extraction step speaks "employers"/"associates"; merge maps
    # them onto affiliations/known_associates without the caller adapting.
    p = _jane()
    p2 = p.merge(
        {
            "employers": [{"organization": "Nortel", "title": "Engineer"}],
            "associates": ["John Smith"],
        }
    )
    assert "Nortel" in p2.employers
    assert "John Smith" in p2.known_associates


def test_merge_accepts_handles_as_platform_dict():
    p = _jane()
    p2 = p.merge({"handles": {"reddit": "u/jdoe"}})
    keys = {h.key() for h in p2.handles}
    assert ("reddit", "u/jdoe") in keys
    # Existing bluesky handle survives the merge.
    assert ("bluesky", "jdoe") in keys


def test_merge_dedupes_handles_by_platform_and_handle():
    p = _jane()
    # Same platform + same handle (differing case / leading @) -> one entry.
    p2 = p.merge({"handles": {"bluesky": "JDOE"}})
    bluesky = [h for h in p2.handles if h.platform.casefold() == "bluesky"]
    assert len(bluesky) == 1


def test_merge_does_not_blank_existing_scalars():
    p = _jane().merge({"wikidata_qid": "Q123"})
    # An update that omits wikidata_qid must not erase it.
    p2 = p.merge({"aliases": ["Janey"]})
    assert p2.wikidata_qid == "Q123"


def test_merge_ignores_unknown_keys():
    p = _jane()
    # An over-eager extractor emitting junk keys must not crash enrichment.
    p2 = p.merge({"favourite_colour": "blue", "aliases": ["Janey"]})
    assert "Janey" in p2.aliases
