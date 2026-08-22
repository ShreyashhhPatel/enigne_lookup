"""Canonicalization + near-duplicate detection — half of the dedup problem.

Two independent jobs, both pure functions (no I/O, no LLM, deterministic):

1. `canonicalize_url` collapses the cosmetic variants of a link (tracking
   params, www, trailing slash, http-vs-https, fragment) into one canonical
   dedup key. This catches *exact* re-shares of the same URL.

2. `simhash` + `cluster_near_duplicates` catch *syndication*: the same wire
   story re-run by 47 outlets under 47 different URLs with lightly edited
   bodies. SimHash gives near-identical documents near-identical fingerprints,
   so a small Hamming distance means "same story."

The clustering deliberately keeps ONE representative per cluster plus the full
member list — because "47 outlets ran this" is itself a signal worth surfacing,
not just noise to discard.

Everything here is a plain function the pipeline calls. None of it belongs in
the LangGraph graph (see docs/CONSTRAINTS.md).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# URL canonicalization
# ---------------------------------------------------------------------------

# Query params that carry tracking/attribution, never content. Dropped whole.
_TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "fbclid", "gclid", "dclid", "gbraid", "wbraid", "msclkid", "yclid",
        "mc_cid", "mc_eid", "igshid", "igsh", "_hsenc", "_hsmi", "vero_id",
        "ref", "ref_src", "ref_url", "referrer", "source", "cmpid", "ncid",
        "spm", "scm", "share", "s_cid", "cid", "ito",
    }
)

# Params whose *prefix* marks them as tracking (utm_source, utm_campaign, ...).
_TRACKING_PREFIXES: tuple[str, ...] = ("utm_",)

_DEFAULT_PORTS = {"http": "80", "https": "443"}


def canonicalize_url(url: str) -> str:
    """Return a canonical dedup key for `url`.

    The output is meant as a *comparison key*, not a guaranteed-fetchable URL:
    we intentionally normalize http->https and strip `www.` so that trivially
    different links to the same page collapse together. Two URLs that point at
    the same content should produce the same string.

    Rules: lowercase scheme+host, force https, drop leading `www.`, drop default
    ports, drop tracking params (exact + `utm_*`), sort remaining params for
    stability, drop the fragment, and strip a trailing slash from non-root paths.
    """
    raw = (url or "").strip()
    if not raw:
        return ""

    # Give a scheme-less input something to parse so the host lands in netloc
    # rather than path ("example.com/x" would otherwise parse as all-path).
    if "//" not in raw.split("?", 1)[0]:
        raw = "https://" + raw

    parts = urlsplit(raw)

    scheme = "https" if parts.scheme.lower() in ("http", "https") else parts.scheme.lower()

    host = parts.hostname or ""
    if host.startswith("www."):
        host = host[4:]

    # Reattach the port only when it's non-standard. Both 80 and 443 are
    # dropped regardless of scheme: we force https above, so an original
    # `http://host:80` must still collapse onto `https://host` rather than
    # keeping :80 (which is not https's default but is still a default web port).
    netloc = host
    if parts.port and str(parts.port) not in _DEFAULT_PORTS.values():
        netloc = f"{host}:{parts.port}"

    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
        and not k.lower().startswith(_TRACKING_PREFIXES)
    ]
    kept.sort()
    query = urlencode(kept)

    # Fragment dropped entirely — it never changes which document this is.
    return urlunsplit((scheme, netloc, path, query, ""))


# ---------------------------------------------------------------------------
# SimHash near-duplicate detection
# ---------------------------------------------------------------------------

_HASH_BITS = 64
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _shingles(text: str, size: int) -> list[str]:
    """Word-level k-shingles of the normalized text.

    `size=1` (the default) is plain unigram tokens — measured to be the most
    robust choice for *syndication*: when an outlet wraps the wire copy in its
    own intro/outro, unigram fingerprints barely move, whereas n-gram shingles
    at the seams flip many bits. Pass `size>=2` when word order matters more than
    robustness to boilerplate. Falls back to unigrams when the text is shorter
    than one shingle.
    """
    tokens = _TOKEN_RE.findall(text.lower())
    if size <= 1 or len(tokens) < size:
        return tokens
    return [" ".join(tokens[i : i + size]) for i in range(len(tokens) - size + 1)]


def _hash64(feature: str) -> int:
    """Stable 64-bit hash of a feature string.

    blake2b, NOT Python's built-in hash() — the latter is salted per process,
    which would make fingerprints non-reproducible across runs.
    """
    return int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "big")


def simhash(text: str, shingle_size: int = 1) -> int:
    """Charikar SimHash of `text` as a 64-bit integer.

    Similar texts -> similar fingerprints (small Hamming distance). Each bit is
    a majority vote across the hashed shingles: +1 where a shingle's hash has
    that bit set, -1 where it doesn't; the sign of the sum is the output bit.
    """
    features = _shingles(text, shingle_size)
    if not features:
        return 0

    vector = [0] * _HASH_BITS
    for feature in features:
        h = _hash64(feature)
        for bit in range(_HASH_BITS):
            vector[bit] += 1 if (h >> bit) & 1 else -1

    fingerprint = 0
    for bit in range(_HASH_BITS):
        if vector[bit] > 0:
            fingerprint |= 1 << bit
    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    """Number of differing bits between two fingerprints."""
    return (a ^ b).bit_count()


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------


class DuplicateCluster(BaseModel):
    """A group of near-duplicate documents.

    `representative_id` is the single copy worth keeping; `member_ids` is the
    full group (including the representative). `size` is how many outlets ran
    it — surface this, don't just discard the dups.
    """

    representative_id: str
    member_ids: list[str]
    size: int


class _UnionFind:
    """Minimal union-find to group transitively-connected near-dups."""

    def __init__(self, ids: list[str]) -> None:
        self._parent = {i: i for i in ids}

    def find(self, x: str) -> str:
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        # Path compression.
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        self._parent[self.find(a)] = self.find(b)


def cluster_near_duplicates(
    documents: Iterable[tuple[str, str]],
    threshold: int = 6,
    shingle_size: int = 1,
) -> list[DuplicateCluster]:
    """Group `(id, text)` documents into near-duplicate clusters.

    Two documents are near-duplicates when their SimHash fingerprints differ by
    at most `threshold` bits. With the unigram default, measured distances are
    ~2-5 for genuine re-runs of the same story (including outlet intros) and 30+
    for unrelated stories, so `threshold=6` separates them with wide margin
    while NOT collapsing independent coverage of the same event (that shares
    topic vocabulary but is not the same text). Clustering is transitive via
    union-find: A~B and B~C puts A, B, C together.

    The representative of each cluster is the LONGEST text (the fullest version
    of the story), tie-broken by smallest id for determinism. Returned clusters
    are sorted largest-first, so the most-syndicated stories come first.

    Note: O(n^2) pairwise comparison — fine for the per-target batch sizes here.
    Swap in LSH banding if this ever runs over a firehose-scale set.
    """
    docs = list(documents)
    if not docs:
        return []

    ids = [d[0] for d in docs]
    text_by_id = {d[0]: d[1] for d in docs}
    fp_by_id = {d[0]: simhash(d[1], shingle_size) for d in docs}

    uf = _UnionFind(ids)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if hamming_distance(fp_by_id[ids[i]], fp_by_id[ids[j]]) <= threshold:
                uf.union(ids[i], ids[j])

    groups: dict[str, list[str]] = {}
    for i in ids:
        groups.setdefault(uf.find(i), []).append(i)

    clusters: list[DuplicateCluster] = []
    for members in groups.values():
        representative = max(members, key=lambda i: (len(text_by_id[i]), _neg_id(i)))
        clusters.append(
            DuplicateCluster(
                representative_id=representative,
                member_ids=sorted(members),
                size=len(members),
            )
        )

    clusters.sort(key=lambda c: (-c.size, c.representative_id))
    return clusters


def _neg_id(i: str) -> tuple[int, ...]:
    """Sort helper: makes the lexicographically-smallest id win a length tie
    inside `max(...)` (max wants the "largest" key, so invert the codepoints)."""
    return tuple(-ord(ch) for ch in i)
