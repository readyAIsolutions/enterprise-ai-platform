# STATUS_DEMIURGE_POSITION_ADDRESSED_MEMORY

**Module:** `position_addressed_memory`
**Source transcript:** JEVanClief — *"How I Run Creative, Software, and Business Work as One System"*
(`data/transcripts/JEVanClief/hALln9wrrQo.md`)
**Branch:** `upgrade/demiurge-enterprise-boost`

## What the transcript teaches (understood technique)

JEVanClief runs creative, software, and business work as **one system** whose
carrier is a single folder ("one folder as my app"). The transcript frames this
as three competing bets on what "memory" means for an LLM:

1. **OpenBrain / vector embeddings — CONTENT addressed**: "take everything
   you've ever written, turn it into numbers, ask the model to find what's
   similar … slow to set up, expensive to maintain … brittle" (returns "nine
   vaguely related notes").
2. **Karpathy's LLM wiki — LINK addressed**: agent-maintained markdown entity
   pages, "contradictions are flagged, orphan pages are found"; trade-off is a
   maintenance LLM "running constantly".
3. **The folder system — POSITION addressed**: "the folder you already have and
   your own brain."

The position-addressed mechanic is a **cascading markdown context**:
> "Claude.md at the root cascades down. Context.md inside the project layers on
> top. By the time Claude reads the scene, it has already inherited the brand
> voice, the production rules, the specific shot list. Nothing got embedded,
> nothing's getting retrieved. The location of the information and the actual
> routing of it did the work."

It generalizes familiar scoping ("Unix environment variables scope down, CSS
specificity scopes down") — "the folder name is a namespace, the namespace
carries meaning. We just didn't have a model that could read it before."
JEVanClief judges position as "the cheapest, the fastest, and the only one
that's still legible to a human."

## Module API

Pure-logic core in `modules/position_addressed_memory/position_addressed_memory.py`:

- `ContextRule` — a single inherited rule (key, title, value, source, path, order),
  with `is_root`, `to_dict`/`from_dict`.
- `parse_markdown_context(content, path, source, order)` — parses `## Heading`
  blocks and `key: value` lines into `ContextRule`s.
- `ContextStack(root, rule_files, precedence, loader)` — walks a path root→leaf
  collecting inherited layers; `collect`, `rules_for`, `resolve` (merged map),
  `resolve_rule`. `Precedence.DEEPEST` (project layers on top, default) vs
  `Precedence.SHALLOWEST` (root wins). Includes the target file as the deepest
  layer (per-file scene/convention doc).
- `PathResolver(root)` — `resolve` returns `PathResolution` (namespaces,
  filename, depth); `is_within`, `relative`, `namespace_path` ("the folder name
  is a namespace").
- `ContentStore` — content-addressed store by SHA-256 digest, dedup,
  `lookup`/`contains`.
- `LinkStore` — link-addressed wiki pages: `define`, `reference`, `resolve`,
  `target`, `orphans()` (referenced-but-never-defined), `contradictions()`
  (name→multiple targets).
- `MemoryAddressing(root, ...)` — model over all three addressing modes with a
  **deterministic** `resolve(query)` that classifies a 64-hex string as
  content, a path under root as position, otherwise as link. Exposes
  `resolve_position` / `resolve_content` / `resolve_link` /
  `inherited_context`.
- Position hits carry both the file content and the full inherited context map
  (brand voice, production rules, shot list).

Platform module `PositionAddressedMemoryModule` (`__init__.py`): lifecycle
`initialize` / `health_check` / `shutdown`, config `{root, rule_files,
precedence}`, event-bus facade publishing `position_addressed_memory.*` events,
`stats()`.

## Verification (PASS)

| Check | Command | Result |
|-------|---------|--------|
| Unit tests | `python3 -m pytest modules/position_addressed_memory/tests -q` | **PASS — 20 passed** |
| Registration | import → `'position_addressed_memory' in _MODULE_REGISTRY` | **True** |

Test coverage: markdown rule parsing + serialization; root CLAUDE.md cascade;
project Context.md layering (deepest wins); SHALLOWEST precedence; root-outside
guard; path namespace resolution; content SHA-256 dedup; link orphans +
contradictions; deterministic resolution by content-hash / position /
link-name; inherited full cascade; module lifecycle (healthy/unhealthy/event
publish).

## UNVALIDATED / assumptions

- **Stdlib-only, network-free:** confirmed by construction (hashlib, dataclasses,
  pathlib, enum only). No numpy/pandas/requests imported.
- **`Precedence.DEEPEST` as default** is the transcript-faithful reading
  ("Context.md layers on top"); the alternative `SHALLOWEST` is provided and
  tested.
- **Position content** falls back to reading the local file when not stored in
  memory; this is a local filesystem read (no network) — validated only in the
  deterministic store tests, not across a distributed filesystem.
- **Real transcript grounding** is the source of truth for feature scope; only
  features present in the transcript were implemented (no invented features).
- **Ledger / config.yaml / platform_kernel.py untouched** per contract.
