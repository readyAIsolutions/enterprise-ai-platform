# STATUS: DEMIURGE — Second Brain module

Status: PASS (built, tested, committed, manifest updated)
Branch: upgrade/demiurge-enterprise-boost
Module: modules/second_brain  (version 1.0.0)

## What builds R here (real transcript grounding)

The module source is grounded in three REAL pulled JE Van Clief transcripts:

  1. "-CUsfao6m7E"  Your Second Brain Is Not a Notes App
     - Core thesis: a second brain must NOT be a note bucket. Plainly
       "put it into a bucket and that's it ... ends up becoming a graveyard".
       → implemented as: storage-only archives are flagged "storage only";
       value comes from linking ideas (edges) + retrieval by concept.
     - "A node is going to be some sort of description, some sort of thing.
       An edge is how that connects to other things." → capture() nodes,
       link_ideas() edges, connected_component() cluster traversal.
     - "It's metadata in a certain way ... it captures and isolates my
       thinking." → capture stores tags+source metadata, not blobs.
     - "you're helping it create the connections ... I am stopping it from
       needing to make those connections." → the engine records links so the
       AI doesn't have to rediscover relationships.

  2. "mme027WZhgo"  Van Squared: A Free Local AI Model Labeled a 26-Year Archive
     - "navigate 20 years of video"/"change the tags" → the labeled long
       archive that stays searchable. Implemented via tags + query_concept
       + build_compounding_report (compounding over a long archive).

  3. "lDXCkx3Nla8"  AI Since 2011: The Ideas That Outlive Every Model
     - Ideas/first-principles outlive any single model/tool → the second brain
       is the compounding archive of ideas, not the tool. Implemented via
       build_compounding_report's compound_score (growth + linkage +
       resurfacing - isolated/lonely notes).

## What adds R (reusability) to this repo

- Pure, network-free engine (SecondBrain + Entry) that is unit-testable in
  isolation — matches the contract of context_routing / shared_workspace.
- Spaced-repetition resurfacing: entries carry next_review, review()/forget()
  with doubling intervals (1→2→4… capped 32 days). Keeps a second brain from
  becoming a static graveyard — genuinely reusable "retrieval prompts".
- Concept-based query (query_concept) instead of folder traversal; tag
  normalization; bidirectional idea linking + graph cluster traversal.
- build_compounding_report() exposes link density / isolated count / verdict
  ("compounding" vs "storage only") — directly reusable for any KB module.

## What to DROP (honest limits)

- This is an in-memory store (dicts). It deliberately does NOT persist to
  disk / DB / graph DB. Drop or replace persisting=false if you need durability
  — that is out of scope here (kept pure + network-free for testability).
- The conversational / screen-walkthrough parts of the "Notes App" transcript
  (Obsidian UI, node-graph visualization) are NOT implemented — only the
  mechanisms behind them. No graph rendering/visualization.
- No cross-module integration (e.g. KB-backed retrieval from rag/ or
  knowledge_graph) yet — wiring is a separate task.

## Test / build board

- python3 -m pytest modules/second_brain/tests -q
    → 14 passed in 0.04s                 [PASS]
- _MODULE_REGISTRY registration check
    → REGISTERED: True | name: second_brain | version: 1.0.0  [PASS]
- Module health
    → HealthStatus.HEALTHY after initialize()                [PASS]
- Manifest data/build/manifest.json
    → -CUsfao6m7E, mme027WZhgo, lDXCkx3Nla8  → status "built", module
      "second_brain"; built_modules += "second_brain"         [PASS]

## Files

- modules/second_brain/__init__.py            (module wrapper + @module)
- modules/second_brain/second_brain.py        (pure engine)
- modules/second_brain/tests/test_second_brain.py  (14 tests)
- data/build/manifest.json                    (updated)
- STATUS_DEMIURGE_SECOND_BRAIN.md             (this file)
