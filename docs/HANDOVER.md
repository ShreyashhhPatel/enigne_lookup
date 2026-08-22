# Handover

A living record of where things stand right now — read this first. Not a dump
of everything; just what's done, what's next, and how to verify.

_Last updated: 2026-08-22, end of Step 3._

## Where things stand

**Step 3 is complete: `Document` model + GDELT source adapter.**

Done so far:
- **Step 1** — package skeleton, backbone docs, `entity.py` (`EntityProfile`
  and friends) with a pure `merge()`. 10 tests.
- **Step 2** — `dedup.py`: `canonicalize_url` + SimHash near-dup clustering
  (`simhash` / `hamming_distance` / `cluster_near_duplicates`), defaults
  calibrated empirically. 15 tests.
- **Step 3** — `document.py` (`Document`: a normalized *mention*, auto-computes
  its `canonical_url`, exposes `dedup_text`) and the `sources/` package:
  `sources/base.py` (injectable `Fetcher` protocol + stdlib `UrllibFetcher` +
  `RateLimited`/`SourceError`) and `sources/gdelt.py` (`GdeltSource`: builds
  DOC 2.0 artlist queries, self-throttles to 1 req/5s, parses articles to
  Documents, handles 429 and plaintext-200 rate-limit notices). 13 tests.

## How to verify (Test checklist)

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
./.venv/bin/python -m pytest -q
```

Expected: `38 passed`. **Last run: 38 passed in 0.09s (verified 2026-08-22).**

### Live-verification status (be honest about this)
- The GDELT parser is unit-tested against the documented artlist JSON shape via
  a `FakeFetcher` — **no live happy-path parse has been confirmed yet.**
- The **`RateLimited` path IS live-verified**: real calls to GDELT from this
  environment return HTTP 429 (the IP is in GDELT's rate-limit window), and the
  client correctly raises `RateLimited`.
- **TODO:** confirm the happy-path parse against a live 200 response from a
  non-rate-limited network. Quick check:
  ```bash
  PYTHONPATH=src ./.venv/bin/python -c "from engine_lookup.sources.gdelt import GdeltSource; print(len(GdeltSource(min_interval=0).search('\"Christine Lagarde\"', timespan='3d', max_records=3)))"
  ```

## What's next (proposed order)

Each is its own reviewable step + push:

1. **Article body extraction** — fetch + extract the body for a Document (e.g.
   trafilatura) so dedup fingerprints real bodies, not just titles. Small,
   isolated, and unlocks better dedup. _Could slot in here or after matching._
2. **More source adapters** — Bluesky (AT Protocol, free real-time social),
   Guardian, Reddit. Each is a new `Source` reusing the `Fetcher` seam.
3. **Candidate matching** — high-recall alias/fuzzy match of Documents against
   `EntityProfile.match_terms`. Deliberately over-fires.
4. **Entity linking** — feature-based scoring + tiered LLM adjudication.
5. **LangGraph investigation loop** — state, nodes, budget/saturation routing,
   Postgres checkpointer. The enrichment feedback loop is the headline feature.
6. **Digest/synthesis + CLI entrypoint.**

## Watch out for / open threads

- Python here is **3.14**; pin nothing lacking 3.14 wheels. pydantic 2.13.4 +
  pytest verified. LangGraph install on 3.14 still **unverified**.
- **GDELT rate limit is real:** 1 request / 5 seconds, enforced per IP, and it
  can arrive as HTTP 429 *or* an HTTP 200 with a plaintext notice. `GdeltSource`
  handles both; keep the 5s throttle when polling for real.
- GDELT gives metadata only — Documents have empty `text` until body extraction
  lands; `dedup_text` falls back to the title meanwhile (weak signal).
- `canonicalize_url` output is a comparison KEY, not a fetch URL. Fetch `url`.
- Two-source attestation stays in the future `update_profile` node.
- `cluster_near_duplicates` is O(n²) — fine per-target; LSH later if needed.
