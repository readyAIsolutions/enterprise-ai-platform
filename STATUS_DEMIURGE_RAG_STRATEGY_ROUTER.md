# STATUS — `rag_strategy_router` (DEMIURGE)

Intent-based **VECTOR / GRAPH / HYBRID** RAG strategy router, grounded entirely
in the real transcript `ColeMedin/p0FERNkpyHE.md` — *"Introducing RAG 2.0:
Agentic RAG + Knowledge Graphs (FREE Template)"*.

## PASS/FAIL board

| Check | Command | Result |
|-------|---------|--------|
| Unit tests | `python3 -m pytest modules/rag_strategy_router/tests -q` | **PASS — 55 passed in 0.11s** |
| Registration | `... _MODULE_REGISTRY ... print('rag_strategy_router' in _MODULE_REGISTRY)` | **True** |
| Lint/syntax | write-time checks on `core.py` / `__init__.py` / tests | clean |

## What was understood from the transcript

The talk combines **two retrieval strategies** and lets an agent *"pick and
choose how it explores the knowledge"* per query:

- **Vector database** (Postgres + pgvector, chunked/embedded docs — "traditional
  rag" semantic similarity) for **single-entity / broad-semantic fact lookups**:
  *"what are the AI initiatives for Google"* → *"it just did a simple vector
  search ... it doesn't need to do the knowledge graph in this case."*
- **Knowledge graph** (Neo4j + Graphiti; entities as nodes, typed relationships
  as edges — `Amazon --invested_in--> Anthropic`, `Anthropic --runs_on--> AWS`,
  `Microsoft --partnered_with--> OpenAI --hosted_on--> Azure`) for
  **relational / multi-entity** questions: *"how are OpenAI and Microsoft
  related"* → *"the kind of thing that would definitely call for a query to our
  knowledge graph."*
- **Both (hybrid)** when a query carries both intents or explicitly asks: *"what
  are the initiatives for Microsoft? how does that relate to anthropic? use both
  search types"*; author's system prompt: *"use the knowledge graph tool only
  when the user asks about two companies in the same question ... Otherwise just
  use the vector store tool. Combine both approaches only when you are asked to
  do so."*

This module models exactly that **routing decision** — it is a
**router/dispatcher**, NOT another retriever, and depends on none of the
existing `agentic_rag` / `knowledge_graph` / `rag` / `hybrid_kg_retrieval`
modules.

## Public API

- `Strategy` enum: `VECTOR` / `GRAPH` / `HYBRID` (+ `from_value`, `all_strategies()`).
- `Signal`: a transcript-grounded regex routing signal (name, strategy, pattern, weight).
- `RouteDecision` dataclass: `strategy`, `confidence` (0–1), `matched_signals`,
  `rationale`, `scores`, `query`, `.as_dict()`.
- `QueryClassifier(signals=?, weights=?, hybrid_margin=0.34, default_strategy=VECTOR)`
  → deterministic `.classify(query) -> RouteDecision`.
- `StrategyRouter`: `route(query)`, `route_batch(queries)`,
  `register_retriever(strategy, fn)`, `unregister_retriever`,
  `registered_strategies()`, and `dispatch(query, *, retrievers=...) -> dict`
  which calls the injected callable retriever for the chosen strategy (pure,
  network-free).
- `RagStrategyRouterModule(Module)` + `create_rag_strategy_router_module(config)`
  factory; facade methods `route` / `route_batch` / `dispatch` /
  `register_retriever` / `strategies`, `set_event_bus`, async
  `initialize`/`health_check`/`shutdown`.

Config defaults: `hybrid_margin=0.34`, `default_strategy="vector"`,
`signal_weights={}`.

## Routing logic (deterministic)

1. Each matching signal adds `base_weight * weight_override` to its strategy.
2. Explicit "use both" HYBRID signals → HYBRID outright.
3. Else both GRAPH and VECTOR fired and balanced within `hybrid_margin` → HYBRID.
4. Else highest score wins; **VECTOR breaks ties** (transcript default
   "otherwise just use the vector store tool").
5. No signal → fall back to configured default strategy, confidence `0.0`.

## UNVALIDATED / limitations

- **No temporal/point-in-time facet.** This transcript never discusses temporal
  facts, "what changed over time", or bitemporal graph edges, so NO temporal
  signal was invented. (If grounding a temporal router, a different source would
  be required.)
- Signals are English keyword/regex heuristics tuned to the transcript's
  big-tech/AI-initiatives demo domain; they are not learned and not benchmarked
  against a labeled query set.
- The `two_entity_conjunction` signal relies on capitalized entity tokens; lower-
  cased or non-English entity names may not trigger it.
- Retrievers are fully injected; no real vector store / knowledge graph is
  included (by design — this is the dispatcher only).
