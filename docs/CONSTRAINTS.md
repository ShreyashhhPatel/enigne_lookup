# Constraints

A short, explicit list of what this system must not do, and the boundaries it
operates within. "Allow" should never mean "allow anything."

## Legal / ethical boundary (the important one)

- **Public figures' public statements and coverage only, by default.**
  Monitoring what a public figure says publicly and how they are covered is
  standard practice — every PR firm, newsroom, and IR team does it. Building a
  persistent behavioural dossier on a *private individual* is a categorically
  different thing, legally and ethically.
- **`entity_type` is mandatory on every target.** Enforced in the model
  (`EntityProfile` has no default for it). Private-individual monitoring is
  restricted to consented contexts (e.g. candidate screening with disclosure,
  or monitoring your own name) — never ad hoc.
- **Applicable regimes:** PIPEDA (Canada) and GDPR (any EU-based target).
  Treat "is this person a private individual in the EU?" as a hard gate, not an
  afterthought.
- No compiling of personal information across sources for private individuals.

## Source / ToS boundary

- **No X full-archive scraping.** Full-archive search is Enterprise-only
  (~$42k/mo as of 2026); do not attempt to route around that. X is out of v1
  entirely.
- **Prefer official APIs and open protocols** (GDELT, Guardian, PRAW/Reddit,
  Bluesky AT Protocol). Third-party scraper gateways for closed platforms
  (LinkedIn, Instagram, Facebook, TikTok) sit in a ToS grey zone and break
  without warning — acceptable only for throwaway experiments, never a
  dependency of the product.
- Respect robots.txt and rate limits on any direct article fetching.

## Engineering boundaries

- **Keep pure functions out of the LangGraph graph.** Dedup, URL
  canonicalization, and fetching are plain functions the nodes call. The graph
  is only for nodes that call a model or make a routing decision.
- **The investigation loop must have hard stops** — budget (tool calls / tokens
  / wall clock), a max-iteration cap, and a saturation check. No open-ended
  loops. The recursion limit is a backstop, not the primary guard.
- **Two-source attestation before promoting a fact** into a profile. One blog
  claiming a handle is noise; two independent sources is signal. This is what
  stops profile drift onto the wrong person.
- Secrets (API keys) come from the environment, never committed.
