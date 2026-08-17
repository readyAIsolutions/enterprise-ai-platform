# Module: `ai_memory_hierarchy`

- Category: Knowledge Intake · priority 1
- Version: 1.0.0
- Purpose: Layered memory model for agents (working/short/long) from AI-memory transcripts.
- Skill: `eni-module-ai_memory_hierarchy` (ICM stages) in skills_pack/skills/eni-modules/ai_memory_hierarchy/

## What it does
AI Memory Hierarchy — an enterprise module modeling the AI memory hierarchy.

Grounded in the JEVanClief transcript *"How a 1953 Word Game Explains AI
Memory"* (https://www.youtube.com/watch?v=S3fXSc5z2n4). The transcript maps the
hardware memory hierarchy (speed-vs-capacity tradeoff, locality-based staging)
onto AI memory:

  - model weights  ~ ROM            (read-only, fixed at training time)
  - context window ~ working memory / RAM (temporary, per-conversation)
  - system prompt  ~ firmware       (operating parameters)
  - retrieved ctx  ~ disk -> RAM on demand (query-driven loading)
  - persistent mem ~ selectively loaded summaries kept between conversations

Key insight implemented here: in AI, code and data are the *same* — everything
is text processed identically, so a single string-typed store with a
locality/access-count promotion policy models the whole hierarchy.

The deterministic core lives in
:mod:`enterprise.modules.ai_memory_hierarchy.ai_memory_hierarchy`
(``MemoryHierarchy``); this package exposes it as a registered Platform Kernel
module with an initialize / health_check / shutdown lifecycle and a thin
facade. Stdlib-only and network-free.

## Key API (facade methods)
demote, health, health_check, hierarchy, initialize, insert, lock_weights, promote, retrieve, set_event_bus, set_prompt, set_weights, shutdown, tier_summary

## Tests
```bash
python3 -m pytest modules/ai_memory_hierarchy/tests -q
```

## Import
```python
from enterprise.modules.ai_memory_hierarchy import create_ai_memory_hierarchy_module
m = create_ai_memory_hierarchy_module()
```
