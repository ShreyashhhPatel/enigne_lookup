# Architecture

A high-level map of the system — the shape of the thing, not implementation
detail. Kept current so no session has to re-derive the terrain.

## Guiding principle

Two problems dominate everything: **entity disambiguation** (is this the right
person?) and **deduplication** (is this the same story?). The architecture is
organized around solving those two, not around "search."

## Two layers

```
                 ┌─────────────────────────────────────────────┐
   SOURCES  ───► │  BREADTH: deterministic pipeline (no LLM)    │
  news/social    │                                              │
                 │  ingest → canonicalize URL → dedup (SimHash) │
                 │        → candidate match → salience          │
                 └───────────────────┬─────────────────────────┘
                                     │  candidate mentions +
                                     │  the EntityProfile
                                     ▼
                 ┌─────────────────────────────────────────────┐
   DIGEST   ◄─── │  DEPTH: LangGraph investigation loop (LLM)   │
   / alerts      │                                              │
                 │  plan → search → adjudicate → update_profile │
                 │        → route(budget, saturation) ↺         │
                 └─────────────────────────────────────────────┘
```

**Why the split matters.** Ingestion is high-volume and mostly branch-free —
running it through an LLM is how these projects become unaffordable. Per-target
investigation is where reasoning, backtracking, and self-correction pay off.
Keep pure functions (dedup, URL canonicalization, fetching) *out* of the graph;
the graph holds only nodes that call a model or make a routing decision.

## The connective tissue: EntityProfile

`src/engine_lookup/entity.py` — the canonical record for a tracked person.
Every stage depends on it:

- **dedup** groups mentions that are about the same entity,
- **candidate matching** fuzzy-matches against its `match_terms`,
- **entity linking** scores context against its `employers`, `roles`,
  `locations`, `handles`, and `known_associates`,
- the **investigation loop** enriches it — new aliases/handles discovered in
  pass one make pass two find more. That feedback loop is the product.

## Component map (target state)

| Component            | Layer     | Uses an LLM? | Status        |
|----------------------|-----------|--------------|---------------|
| `entity.py`          | shared    | no           | **built**     |
| URL canonicalization | breadth   | no           | **built**     |
| Near-dup clustering  | breadth   | no           | **built**     |
| Source pollers       | breadth   | no           | planned       |
| Candidate matching   | breadth   | no           | planned       |
| Entity linking       | breadth¹  | tiered²      | planned       |
| Investigation graph  | depth     | yes          | planned       |
| Digest / synthesis   | depth     | yes          | planned       |

¹ Runs in the pipeline but feeds the graph.
² Feature-based scoring resolves 80–90% of cases; only ambiguous ones hit an LLM.

## Sources (v1 scope)

GDELT + Guardian Open Platform + Reddit + Bluesky. Public figures only.
X is deliberately excluded from v1 (most expensive, least differentiating).
See `docs/DECISIONS.md`.
