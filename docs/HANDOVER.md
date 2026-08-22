# Handover

A living record of where things stand right now — read this first. Not a dump
of everything; just what's done, what's next, and how to verify.

_Last updated: 2026-08-22, end of Step 1._

## Where things stand

**Step 1 is complete: repo foundation + the `EntityProfile` model.**

Done:
- Package skeleton (`src/` layout, `pyproject.toml`, `.gitignore`, `README.md`).
- The four backbone docs: ARCHITECTURE, CONSTRAINTS, DECISIONS, HANDOVER.
- `src/engine_lookup/entity.py` — `EntityProfile`, `EntityType`, `Handle`,
  `Affiliation`, with derived views (`employers`, `roles`, `handle_values`,
  `match_terms`) and a pure, de-duplicating `merge()`.
- `tests/test_entity.py` — 10 tests covering the required-`entity_type`
  guardrail, derived views, and merge semantics (purity, case-insensitive
  de-dup, design-vocabulary aliases, no-blanking of scalars, unknown-key
  tolerance).

## How to verify (Test checklist)

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
./.venv/bin/python -m pytest -q
```

Expected: `10 passed`. **Last run: 10 passed in 0.05s (verified 2026-08-22).**

## What's next (proposed order)

Each is its own reviewable step + push. Bottom-up so every step has a real,
tested contract to build on:

1. **URL canonicalization + near-dup clustering** — pure functions (strip UTM,
   resolve redirects/canonical tags; SimHash/MinHash over article body). Cheap
   to test, no external services, immediately useful. _Likely next._
2. **One real source poller** — start with Bluesky (free AT Protocol firehose)
   or GDELT. Writes normalized records; no LLM.
3. **Candidate matching** — high-recall alias/fuzzy match against
   `EntityProfile.match_terms`. Deliberately over-fires.
4. **Entity linking** — feature-based scoring (org/loc/role/handle/associate
   overlap) with the tiered LLM adjudication fallback.
5. **LangGraph investigation loop** — state schema, plan/search/adjudicate/
   `update_profile`/synthesize nodes, budget + saturation routing, Postgres
   checkpointer. The enrichment feedback loop is the headline feature.

## Watch out for / open threads

- Python here is **3.14**; pin nothing that lacks 3.14 wheels. pydantic 2.13.4
  and pytest verified working. LangGraph install on 3.14 is **unverified** —
  check before committing to it in step 5.
- The two-source attestation rule is NOT in the model by design; it belongs to
  the `update_profile` node (step 5). Don't push it down into `merge()`.
- Keep pure functions out of the eventual graph (see CONSTRAINTS.md).
- `Affiliation.start`/`end` are free-form strings for now; tighten to real dates
  only when a source justifies it.
