# engine_lookup

An entity-centric agent for finding and tracking **particular people** across
news and social media — and, critically, telling *your* Jane Doe apart from the
other 40,000 while recognizing that 300 articles are the same wire story.

The hard part is not search. It is **entity disambiguation** and
**deduplication**. The whole design is built around those two problems.

## The shape of the system

Two layers, drawn along a deliberate line:

- **Breadth — a deterministic pipeline.** Ingest from many sources, canonicalize
  URLs, dedup near-identical stories, cheaply match candidate mentions. No LLM.
  This is a firehose-in, noise-out data pipeline.
- **Depth — a LangGraph investigation loop.** Per-target research that branches,
  backtracks, and *enriches the entity profile as it goes*, so a second pass
  finds more than the first. This is where an LLM earns its place.

The connective tissue between them is the [`EntityProfile`](src/engine_lookup/entity.py) —
the disambiguation anchor every stage reads from.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full map,
[`docs/DECISIONS.md`](docs/DECISIONS.md) for why it is built this way, and
[`docs/CONSTRAINTS.md`](docs/CONSTRAINTS.md) for the boundaries (legal and
technical) it must respect.

## Status

Early, built one reviewable step at a time. See
[`docs/HANDOVER.md`](docs/HANDOVER.md) for exactly where things stand.

- **Step 1 (done):** repo foundation + the `EntityProfile` model and its tests.
- **Step 2 (done):** URL canonicalization + SimHash near-duplicate clustering.
- **Step 3 (done):** `Document` model + GDELT source adapter (injectable fetcher).

## Develop

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
./.venv/bin/python -m pytest
```

## Working method

This project is built following the *AI Collaboration Field Guide*: every step
ships code **and** the documentation that makes it traceable. Decisions get
their "why" recorded, constraints are explicit, and `HANDOVER.md` always
reflects the current state so no session — human or AI — starts cold.
