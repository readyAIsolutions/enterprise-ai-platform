# Pluggable knowledge-source adapters + cross-source merge facade

Reference architecture for "REBUILD a module to MASTER CLASS" work in this repo
(the `kb_bridge` upgrade is the concrete instance). Reusable whenever a module
needs to query across multiple heterogeneous knowledge/document sources and
return one merged, ranked result set — no third-party deps, stdlib only.

## Core components (put in a `sources.py` beside the module)
- `KbDoc` dataclass — normalized result: `id, text, source, metadata, score,
  retrieved_at` (retrieved_at = UTC ISO via `datetime.now(timezone.utc)`).
- `SourceAdapter(ABC)` — `id`, `type` attrs + abstract `query(query, filters=None)
  -> list[KbDoc]`, `list_docs(limit=None)`, `close()`. This is the seam every
  source plugs into.
- Concrete adapters:
  - `FileSourceAdapter(dir, source_id=None)` — recursive `.md/.markdown/.txt`
    reader; `id` = relative path; metadata = path/size/mtime; path+suffix filters.
    Raise `FileNotFoundError` if dir missing.
  - `SqliteSourceAdapter(db, table='docs', auto_create=True)` — real sqlite3
    against `docs(id, text, source, metadata JSON, score)` table; `LIKE` search,
    source/min_score filters, JSON metadata round-trip. Use `sqlite3.Row` +
    `row_factory`.
  - `JsonSourceAdapter(path)` — lazy parse of a JSON ARRAY of doc dicts;
    validate structure (raise ValueError on non-array / missing id/text).
- `SourceRegistry` — `register/get/get_or_create/list/adapters/remove/close`;
    duplicate id -> ValueError, missing -> KeyError.
- `KbMerger` — fan-out query across selected/all adapters -> DEDUPE by id
  (keep highest score) -> RE-RANK by score desc (tie-break source, then id)
  -> apply limit.
- `KbQueryBridge` facade — `register/unregister/list_sources/query(query,
  limit=None, source_ids=None, filters=None)/close`, delegating to a Merger.
- `tokenize(text)` + `score_text(text, query)` — common term-overlap scorer so
  heterogeneous sources (file text vs sqlite rows vs json) rank on the SAME scale.

## Merge semantics (the point of the whole thing)
fan-out -> dedupe-by-id(keep-max-score) -> sort by (-score, source, id) -> limit.

## Lifecycle — keep the whole tree closable in one call
adapter.close() -> registry.close() -> merger.close() -> bridge.close().
Registry clearing on close makes `list_sources() == []` a clean test.

## Module wiring conventions for this repo
- Module factory: `def create_<name>_module(config=None) -> <ModuleSubclass>` in
  `__init__.py` (matches `modules/model_router/__init__.py` convention).
- **Add EVERY new public symbol to `__all__`** — `import *` only exposes `__all__`
  entries; a top-level `create_<name>_module` defined but not in `__all__` is
  silently unreachable via `from pkg import *` (hit this: NameError).

## ENI compressed-file read gotcha (this repo)
- `read_file` and LARGE terminal outputs return `ENI-COMPRESSED ... carrier=...`
  placeholders; real bytes on disk are PLAIN python. Don't trust the placeholder.
- Reliable reads: terminal `grep -nE '^(...)' file` / `sed -n 'a,bp'` / short
  `cat` — SMALL outputs are NOT compressed, only big ones are.
- `search_files` can silently return empty (total 0) on these files — fall back
  to terminal grep when you need real signatures/`def` lines.
- Import root is the PARENT of the repo dir (`~/Desktop/Enterprise Builder`);
  tests auto-insert `parents[4]`. `pytest` from repo cwd works; bare
  `python3 -c ...` / heredoc needs `PYTHONPATH="<parent>"` to import `enterprise`.

## Test patterns that made it green (real, no mocks/stubs)
- tmp_path fixtures writing real `.md/.txt`, a real sqlite `.db` row_factory
  insert, and a real json file.
- Each adapter: query + list_docs + a filter + an error case.
- Merger: cross-source merge, dedupe-keeps-highest (via tiny Fake adapters),
  limit, source-subset, empty-source.
- Facade: cross-source query, limit+subset, lifecycle close.

## Real bug traps (all hit + fixed this session)
- JSON adapter: include a doc ONLY on real text relevance (`score_text > 0`);
  a pre-stored base `score` should BOOST, never gate — otherwise irrelevant
  docs (score>0 from file) leak into results.
- Fixture that does `(tmp / 'notes' / 'c.md').mkdir(parents=True)` creates c.md
  as a DIRECTORY -> later write raises `IsADirectoryError`. mkdir the parent
  dir, then write the file.
- Don't let a per-doc `source` field conflate with the producing adapter id:
  set `doc.source = adapter.id` and stash the item's original `source` in
  `metadata` if you want to keep it.
- When scoring a LIKE-matched sqlite row, ADD the row's stored score to the
  text-relevance score (boost), don't replace it — keeps stored priors useful.
