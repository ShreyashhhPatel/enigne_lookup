# Handover

A living record of where things stand right now — read this first. Not a dump
of everything; just what's done, what's next, and how to verify.

_Last updated: 2026-08-22, end of Step 2._

## Where things stand

**Step 2 is complete: URL canonicalization + near-duplicate clustering.**

Done so far:
- **Step 1** — package skeleton, the four backbone docs, and
  `src/engine_lookup/entity.py` (`EntityProfile` and friends) with a pure,
  de-duplicating `merge()`. 10 tests.
- **Step 2** — `src/engine_lookup/dedup.py`: `canonicalize_url` (collapses
  cosmetic URL variants into a dedup key) and `simhash` / `hamming_distance` /
  `cluster_near_duplicates` (SimHash near-dup detection that groups syndicated
  re-runs, keeping one representative + the full member list so "47 outlets ran
  this" survives as a signal). 15 tests. Defaults were calibrated empirically —
  see the SimHash decision in DECISIONS.md.

Both modules are pure functions / value objects. No I/O, no LLM, no network.

## How to verify (Test checklist)

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
./.venv/bin/python -m pytest -q
```

Expected: `25 passed`. **Last run: 25 passed in 0.07s (verified 2026-08-22).**

## What's next (proposed order)

Each is its own reviewable step + push. Bottom-up so every step builds on a
tested contract:

1. **A `Document`/`Mention` model + one real source poller** — start with
   Bluesky (free AT Protocol firehose) or GDELT. Normalizes fetched items into a
   record carrying `canonical_url` (from Step 2) and text (for SimHash). First
   step that touches the network; keep fetching a plain function, not a graph
   node. _Likely next._
2. **Candidate matching** — high-recall alias/fuzzy match against
   `EntityProfile.match_terms`. Deliberately over-fires.
3. **Entity linking** — feature-based scoring (org/loc/role/handle/associate
   overlap) with the tiered LLM adjudication fallback.
4. **LangGraph investigation loop** — state schema, plan/search/adjudicate/
   `update_profile`/synthesize nodes, budget + saturation routing, Postgres
   checkpointer. The enrichment feedback loop is the headline feature.

## Watch out for / open threads

- Python here is **3.14**; pin nothing that lacks 3.14 wheels. pydantic 2.13.4
  and pytest verified working. LangGraph install on 3.14 is **unverified** —
  check before committing to it in the graph step.
- `cluster_near_duplicates` is O(n²) pairwise. Fine for per-target batches; swap
  in LSH banding if it ever runs over a firehose-scale set.
- `canonicalize_url` output is a comparison KEY, not a guaranteed-fetchable URL
  (it forces https, strips www). Keep the raw URL around separately for fetching.
- Two-source attestation stays in the future `update_profile` node, not in
  `EntityProfile.merge()`.
- `Affiliation.start`/`end` are free-form strings for now; tighten to real dates
  only when a source justifies it.
