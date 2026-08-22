# Decisions

Every meaningful decision and the reasoning behind it. Code shows *what*; this
shows *why*, so settled arguments don't get re-litigated later.

Format: newest at the bottom. Each entry is dated and states the decision, the
why, and any alternative rejected.

---

### 2026-08-22 — Design around disambiguation + dedup, not search

**Decision:** Treat entity disambiguation and deduplication as the core of the
system; "search" is the easy, commoditized part.
**Why:** Naive keyword matching returns high-volume, high-noise results (one
name matches thousands of people; one wire story appears in hundreds of
outlets). The demonstrable value is precision: turning ~200 noisy hits into ~12
correct, linked ones.

### 2026-08-22 — Two layers: deterministic breadth + LangGraph depth

**Decision:** A deterministic pipeline handles ingestion/dedup/matching; a
LangGraph loop handles per-target investigation.
**Why:** Ingestion is high-volume and branch-free — running it through an LLM is
the fast path to an unaffordable system. Reasoning/backtracking pays off only in
per-target depth. The line between them is the main architectural decision.
**Rejected:** One big agent that does everything (cost + unpredictability); a
single linear chain (can't do the enrichment feedback loop).

### 2026-08-22 — EntityProfile is the shared spine, built first

**Decision:** Build `EntityProfile` before anything else.
**Why:** It is the disambiguation anchor every later stage reads from — the
"single highest-leverage thing in the system." Getting it right first gives
dedup, matching, and the graph a stable contract.

### 2026-08-22 — `entity_type` is required, no default

**Decision:** `EntityProfile.entity_type` (public figure vs. private
individual) is mandatory at construction.
**Why:** It is the legal/ethical boundary (see CONSTRAINTS.md). Making it a
required field means no code path can create a target without classifying it.
**Rejected:** A boolean flag or an optional field defaulting to "public" —
defaults are exactly how the wrong default gets shipped.

### 2026-08-22 — `merge()` is pure; attestation lives in the graph

**Decision:** `EntityProfile.merge()` returns a new object and trusts its input;
the two-source attestation rule that gates promotion lives in the future
`update_profile` graph node, not in the model.
**Why:** The graph passes the profile between nodes in its state — in-place
mutation there causes cross-iteration bugs. And attestation needs the candidate
evidence, which is graph state, not something the profile carries. Keep the
model a clean, immutable value object.

### 2026-08-22 — Pydantic v2 for the models

**Decision:** Use pydantic v2 for entity models.
**Why:** Validation for free (enforces the required `entity_type`), clean
(de)serialization for the Postgres checkpointer the graph will use later, and it
is the idiomatic choice in the LangGraph ecosystem. Verified it installs on the
local Python 3.14 before committing to it.

### 2026-08-22 — v1 sources: GDELT + Guardian + Reddit + Bluesky; skip X

**Decision:** Ship the first version on GDELT, Guardian Open Platform, Reddit
(PRAW), and Bluesky (AT Protocol). Exclude X.
**Why:** These are free/cheap and workable. X is the most expensive source
(full-archive is Enterprise-only) and the least differentiating. Bluesky's
firehose is the best open real-time source available right now.

### 2026-08-22 — Document is a *mention*, not an entity; carries a dedup key

**Decision:** `Document` models one fetched item (article/post), separate from
`EntityProfile`. It stores both the raw `url` and a computed `canonical_url`,
and exposes `dedup_text` (body, or title when the body is absent).
**Why:** A fetched item is not yet known to be about our target — linking
decides that later. Keeping raw + canonical URL side by side means we can fetch
the real link but dedup on the stable key. `dedup_text` centralizes the
"body-if-present-else-title" fallback so callers don't re-implement it.

### 2026-08-22 — Injectable `Fetcher`, stdlib urllib default (no HTTP dep)

**Decision:** Sources depend on a tiny `Fetcher` protocol; the default
implementation uses stdlib `urllib`. HTTP errors return their status as data
(e.g. 429) instead of raising.
**Why:** Injecting the fetcher makes every source parser testable without a
network (tests use a `FakeFetcher`). Stdlib urllib avoids adding requests/httpx
for a handful of GETs (keeps deps minimal). Returning the status lets the source
own the back-off decision — a 429 must reach the source logic, not blow up mid-parse.
**Rejected:** requests/httpx as a hard dependency this early (add later if
connection pooling / HTTP2 justify it).

### 2026-08-22 — GDELT: artlist metadata now, article body later

**Decision:** The GDELT adapter uses DOC 2.0 `artlist`, which returns metadata
(url/title/seendate/domain), not body text. Body extraction (trafilatura) is a
separate later step. `GdeltSource` self-throttles to one request / 5s and
surfaces both HTTP-429 and GDELT's plaintext-200 rate-limit notice as
`RateLimited`.
**Why:** artlist is the free, keyless, high-coverage entry point; fetching
bodies for every hit up front is wasteful before candidate matching narrows the
set. The 5s limit and the plaintext-200 quirk were both observed live during
Step 3 and baked into the client rather than left as future surprises.

### 2026-08-22 — SimHash dedup: unigram features, Hamming threshold 6

**Decision:** Near-duplicate detection uses a 64-bit Charikar SimHash over
**unigram** tokens (`shingle_size=1`), clustered with a Hamming-distance
threshold of **6**.
**Why:** Measured against a realistic ~110-word wire story and outlet variants:
unigram fingerprints move only ~2 bits when an outlet wraps the wire copy in its
own intro/outro, ~5 bits for a phrase swap, and ~30 bits for an unrelated story.
Word n-gram shingles (size 2-3) flip 6-13 bits on the same intro/outro because
the shingles at the seams change — worse for exactly the syndication case we
care about. Threshold 6 sits well above genuine re-runs (≤5) and far below
unrelated (30+), so it catches "same text, different wrapper" without collapsing
*independent coverage of the same event* (which shares vocabulary but is not the
same story). Calibrated empirically before fixing the number, not guessed.
**Rejected:** trigram shingles as the default (too brittle to boilerplate);
threshold 3 (misses lightly-edited re-runs at unigram scale).

### 2026-08-22 — canonicalize_url produces a dedup KEY, not a fetch URL

**Decision:** `canonicalize_url` normalizes http→https, strips `www.`, drops
default web ports (80 **and** 443), removes tracking params (`utm_*` + a
click-id list) and the fragment, and sorts remaining params.
**Why:** The output's job is to be a stable comparison key so trivially
different links to the same page collapse. That means being willing to change
the scheme/host cosmetically — acceptable because we never claim the result is
guaranteed-fetchable, only that equal content yields an equal key.

### 2026-08-22 — Postgres over Kafka for v1 ingestion

**Decision:** Use Postgres + a job table for ingestion queueing in v1; introduce
Kafka only when there are many sources and replay is needed.
**Why:** Kafka is overkill for a handful of sources and slows down v1. The
Postgres checkpointer also gives the investigation graph resumability and
incremental monitoring "for free" (resume a thread with an already-enriched
profile) — one storage story for both systems.
