# Module: `position_addressed_memory`

- Category: Legacy Core · priority 46
- Version: 1.0.0
- Purpose: Position-addressed memory — *folder-as-memory* for AI context.
- Skill: `eni-module-position_addressed_memory` (ICM stages) in skills_pack/skills/eni-modules/position_addressed_memory/

## What it does
Position-addressed memory — *folder-as-memory* for AI context.

Grounded in the JEVanClief transcript *"How I Run Creative, Software, and
Business Work as One System"* (https://www.youtube.com/watch?v=hALln9wrrQo).
The transcript contrasts three bets on what memory means for an LLM —
OpenBrain vector embeddings (**content**-addressed), Karpathy's LLM wiki
(**link**-addressed), and **the folder system** (**position**-addressed). This
module implements the position-addressed cascade — a root ``CLAUDE.md`` whose
rules cascade down, per-project ``Context.md`` layered on top, and per-file
convention docs — so "by the time Claude reads the scene, it has already
inherited the brand voice, the production rules, the specific shot list."

The deterministic core lives in
:mod:`enterprise.modules.position_addressed_memory.position_addressed_memory`
(:class:`ContextRule`, :class:`ContextStack`, :class:`PathResolver`,
:class:`MemoryAddressing`); this package exposes it as a registered Platform
Kernel module with an initialize / health_check / shutdown lifecycle and a
thin facade. Stdlib-only and network-free.

## Key API (facade methods)
addressing, health_check, inherited_context, initialize, resolve, resolve_content, resolve_link, resolve_position, set_event_bus, shutdown, stats, store_content, store_link, store_position

## Tests
```bash
python3 -m pytest modules/position_addressed_memory/tests -q
```

## Import
```python
from enterprise.modules.position_addressed_memory import create_position_addressed_memory_module
m = create_position_addressed_memory_module()
```
