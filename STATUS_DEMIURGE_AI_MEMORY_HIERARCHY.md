# STATUS — DEMIURGE UPGRADE WAVE: ai_memory_hierarchy

**Module:** `modules/ai_memory_hierarchy/`
**Source transcript:** `data/transcripts/JEVanClief/S3fXSc5z2n4.md`
  — "How a 1953 Word Game Explains AI Memory" (JEVanClief, 14.4 min / 863s)
**Branch:** `upgrade/demiurge-enterprise-boost`
**Engineer date:** 2026-08-17

## Thesis grounded in the transcript
The episode starts from the 1953 Mad Libs game (Leonard Stern; "clumsy and
naked") and observes that Mad Libs *is* programming at a structural level:
templates with typed blanks, filled according to rules, composed until
something executes. It then maps the **hardware memory hierarchy** onto **AI
memory**:

> "At the base, you have the model weights. This is the closest analog to ROM
> ... fixed at training time." · "the context window ... more like working
> memory" · "you have a system prompt, functions something like a firmware"
> · "retrieved context ... like loading from a disk into RAM. It happens on
> demand." · "persistent memory ... stored between conversations and
> selectively loaded when relevant, almost like summaries."

The transcript stresses the speed-vs-capacity tradeoff, "data moving between
levels, locality patterns determining what gets loaded" — and the crucial
insight that **in AI, code and data are the same thing**: "They are all just
text, all processed identically, all tokens in a sequence."

→ The module models five tiers `[WEIGHTS, WORKING, PROMPT, RETRIEVED,
PERSISTENT]` with a locale/access-count promotion–demotion policy (hot vs
cold), capacity limits per tier, query-driven retrieval (simple keyword
overlap), and a tier summary. Stdlib-only & network-free.

## What was built (public API)
* `MemoryHierarchy` — pure core. `insert(key, content, tier=None)`,
  `retrieve(query, limit)`, `promote(key)`, `demote(key)`, `access(key)`,
  `tier_summary()`, `stats()`, `get(key)`, `clear()`.
* `Tier` enum + `TIERS`; `TIER_RANK`; `MEMORY_TIERS` promotion chain
  `WORKING → RETRIEVED → PERSISTENT`.
* `MemoryEntry` (key, content, tier, access_count, recency, metadata).
* `TierLockedError` + `set_weights` / `lock_weights` (model weights = ROM,
  read-only once trained) and `set_prompt` (system prompt = firmware).
* `tokenize`, `overlap_score` (stdlib `re` keyword/overlap scoring).
* `DEFAULT_CAPACITIES`, `DEFAULT_PROMOTE_THRESHOLD`.
* `AiMemoryHierarchyModule` — ENI `@module(name="ai_memory_hierarchy",
  version="1.0.0", config_defaults={promote_threshold, capacities})` wrapper
  with `initialize` (HEALTHY) / `health_check` / `shutdown`, `set_event_bus`,
  event publishing (`Event.create` via `self._event_bus`, only when bus set),
  and facade methods `insert` / `retrieve` / `promote` / `demote` /
  `tier_summary` / `health` / `set_prompt` / `set_weights` / `lock_weights`.
* `create_ai_memory_hierarchy_module(config)` factory + `__all__`.

## Verification board
| Check | Result | Detail |
|-------|--------|--------|
| Unit tests | **PASS** | 26 passed, 0 failed (0.03s) |
| `pytest modules/ai_memory_hierarchy -q` | **PASS** | `26 passed in 0.03s` |
| Platform registration | **PASS** | `ai_memory_hierarchy in _MODULE_REGISTRY` → **True** |
| Health lifecycle | **PASS** | initialize→HEALTHY; health_check→healthy; shutdown→UNKNOWN |
| Init failure handling | **PASS** | invalid threshold → UNHEALTHY + re-raise |
| Promotion policy (cold→hot) | **PASS** | PERSISTENT→RETRIEVED→WORKING on access-count threshold |
| Capacity eviction | **PASS** | coldest demoted to colder tier; overflow drops from PERSISTENT |
| Retrieval ordering | **PASS** | overlap score, then hotter tier, then access frequency |
| Query-driven promotion | **PASS** | retrieve() counts as locality access |
| Weights = ROM | **PASS** | lock_weights() → TierLockedError on write |
| Tier summary | **PASS** | per-tier count + capacity |
| Network-free | **PASS** | pure stdlib logic, no I/O in core; tmp_path only in tests |

## Files touched (only module + this doc)
* `modules/ai_memory_hierarchy/__init__.py`
* `modules/ai_memory_hierarchy/ai_memory_hierarchy.py`
* `modules/ai_memory_hierarchy/tests/test_ai_memory_hierarchy.py`
* `STATUS_DEMIURGE_AI_MEMORY_HIERARCHY.md` (this file)

No changes to `config.yaml`, `platform_kernel.py`, other modules, or
`data/build/manifest.json`.

## UNVALIDATED
* Full-suite regression: not run, per task constraints (spot-run only).
* Live import inside the full `ModuleRegistry` orchestrator binding not
  exercised end-to-end.
* Retrieval scoring is a simple keyword/overlap count (satisfies "stdlib only,
  no numpy/pandas"); no semantic/embedding retrieval is modeled.
* Real-world promotion thresholds (`promote_threshold`, per-tier capacities)
  are design defaults calibrated to the transcript, not tuned against a
  downstream consumer.
