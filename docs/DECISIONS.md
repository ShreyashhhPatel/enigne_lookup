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

### 2026-08-22 — Postgres over Kafka for v1 ingestion

**Decision:** Use Postgres + a job table for ingestion queueing in v1; introduce
Kafka only when there are many sources and replay is needed.
**Why:** Kafka is overkill for a handful of sources and slows down v1. The
Postgres checkpointer also gives the investigation graph resumability and
incremental monitoring "for free" (resume a thread with an already-enriched
profile) — one storage story for both systems.
