"""Tests for URL canonicalization and near-duplicate clustering."""

from engine_lookup.dedup import (
    canonicalize_url,
    cluster_near_duplicates,
    hamming_distance,
    simhash,
)

# ---------------------------------------------------------------------------
# URL canonicalization
# ---------------------------------------------------------------------------


def test_strips_utm_and_click_ids():
    url = "https://news.example.com/story?utm_source=twitter&utm_medium=social&fbclid=abc&id=42"
    # Tracking params gone; genuine content param (id) kept.
    assert canonicalize_url(url) == "https://news.example.com/story?id=42"


def test_collapses_www_scheme_port_and_trailing_slash():
    a = canonicalize_url("http://www.example.com:80/a/b/")
    b = canonicalize_url("https://example.com/a/b")
    assert a == b == "https://example.com/a/b"


def test_drops_fragment_and_sorts_query():
    url = "https://example.com/p?b=2&a=1#section-3"
    assert canonicalize_url(url) == "https://example.com/p?a=1&b=2"


def test_scheme_less_input_is_parsed_as_host_not_path():
    assert canonicalize_url("example.com/path?utm_source=x") == "https://example.com/path"


def test_two_cosmetic_variants_produce_the_same_key():
    a = "https://www.Example.com/Story/?utm_campaign=z&ref=home"
    b = "http://example.com/Story"
    assert canonicalize_url(a) == canonicalize_url(b)


def test_empty_url_is_empty():
    assert canonicalize_url("") == ""
    assert canonicalize_url("   ") == ""


def test_root_path_slash_preserved():
    # Trailing slash is only stripped from non-root paths.
    assert canonicalize_url("https://example.com/") == "https://example.com/"


# ---------------------------------------------------------------------------
# SimHash
#
# Uses a realistic ~110-word wire story. SimHash near-duplicate detection is a
# property of similar-length, near-identical documents — short snippets don't
# fingerprint meaningfully against full articles, and that's correct behaviour.
# ---------------------------------------------------------------------------

_WIRE = (
    "The central bank raised its benchmark interest rate by half a percentage "
    "point on Tuesday, citing persistent inflation and a resilient labour market "
    "as the primary factors behind a decision that most analysts had widely "
    "anticipated. Officials said further increases could follow if price pressures "
    "fail to ease in the coming months. The move lifts borrowing costs to their "
    "highest level in more than a decade and is expected to ripple through "
    "mortgages, business loans and consumer credit. Financial markets reacted "
    "calmly, with major stock indexes little changed and government bond yields "
    "edging higher after the announcement was released to the public shortly after "
    "midday on the east coast."
)

# A typical outlet re-run: a word or two changed, a phrase swapped.
_WIRE_EDITED = _WIRE.replace("half a percentage point", "50 basis points").replace(
    "Tuesday", "Wednesday"
)
# Same wire copy wrapped in an outlet's own intro/outro.
_WIRE_WRAPPED = "Breaking news. " + _WIRE + " This is a developing story."


def test_identical_text_has_distance_zero():
    assert hamming_distance(simhash(_WIRE), simhash(_WIRE)) == 0


def test_near_identical_text_has_small_distance():
    # A real re-run wire story: small edits stay well within the cluster
    # threshold with the unigram default.
    assert hamming_distance(simhash(_WIRE), simhash(_WIRE_EDITED)) <= 6


def test_unrelated_text_has_large_distance():
    other = (
        "Researchers unveiled a new telescope array in the high desert this week, "
        "promising far sharper images of distant galaxies and faint exoplanets "
        "than any ground-based instrument built before it, with first observations "
        "expected to begin early next year."
    )
    assert hamming_distance(simhash(_WIRE), simhash(other)) > 10


def test_empty_text_fingerprint_is_zero():
    assert simhash("") == 0


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------


def test_syndicated_copies_cluster_unrelated_stays_separate():
    unrelated = (
        "A local bakery took top honours for its sourdough at the county fair "
        "this weekend, beating dozens of entries from across the region in a "
        "contest judged by a panel of visiting pastry chefs and food writers."
    )

    clusters = cluster_near_duplicates(
        [
            ("wire", _WIRE),
            ("outletA", _WIRE_EDITED),
            ("outletB", _WIRE_WRAPPED),
            ("bakery", unrelated),
        ]
    )

    # Two clusters: the 3-way syndication and the lone bakery story.
    assert len(clusters) == 2
    biggest = clusters[0]  # sorted largest-first
    assert biggest.size == 3
    assert set(biggest.member_ids) == {"wire", "outletA", "outletB"}


def test_representative_is_the_longest_version():
    # Three near-duplicate re-runs of similar length; the longest is chosen as
    # the representative (the fullest version of the story).
    copy_a = _WIRE_EDITED
    copy_b = _WIRE
    copy_c = _WIRE + " Additional reporting was contributed by staff across three bureaus."
    clusters = cluster_near_duplicates(
        [("a", copy_a), ("b", copy_b), ("c_longest", copy_c)]
    )
    assert len(clusters) == 1
    assert clusters[0].representative_id == "c_longest"


def test_single_document_is_its_own_cluster():
    clusters = cluster_near_duplicates([("only", _WIRE)])
    assert len(clusters) == 1
    assert clusters[0].size == 1
    assert clusters[0].representative_id == "only"


def test_empty_input_returns_no_clusters():
    assert cluster_near_duplicates([]) == []
