# Additive durable persistence layer (SQLite + in-memory) for an in-memory module

Session-tested pattern: adding durable, provenance-aware SQLite persistence to an
existing **in-memory, dataclass-based** module (e.g. the knowledge_graph module,
modules/knowledge_graph/) WITHOUT breaking any existing API or test. All 157
original tests stayed green and 34 new persistence tests were added (191 total).

## When to use
- A module already has rich in-memory models (Entity, Relationship, Provenance,
  ContradictionRecord) + registries + ingestion, but NO durable store.
- Requirement: "durable + provenance, preserve all tests."
- The user wants it to be additive (new file + thin wiring), not a rewrite.

## Core design decisions (the reusable part)

1. **New file `persistence.py` with one class** (`KGPersistence`), stdlib-only
   (`sqlite3`, `json`) — no new deps, immediately testable.

2. **Dual backend behind one API**: `db_path=None` → in-memory (dict/list
   store mirroring the SQL tables); `db_path=<path>` → SQLite. Both expose the
   exact same methods so tests run identically on both. `db_path` default
   `"data"` (a directory → auto-resolve to `data/knowledge_graph.db`).
   - Path detection pitfall: a not-yet-existing bare path was initially treated
     as a *file*. Fix: treat a path as a directory UNLESS it has a DB extension
     (`.db/.sqlite/.sqlite3/.db3`) OR already exists as a file.

3. **Dedup by composite natural key.** entities table `PRIMARY KEY (type, id)` +
   `INSERT ... ON CONFLICT(type,id) DO UPDATE`. This is the fact key for a
   graph — re-upserting the same (type,id) updates attrs instead of duplicating.
   Relationships dedup by `id`.

4. **Cascade delete** across all three tables in one transaction:
   `DELETE entities WHERE id=?`, `DELETE relationships WHERE from_id=? OR to_id=?`,
   `DELETE provenance WHERE entity_id=?`.

5. **`sync(graph)` / `load()` round-trip.** `graph` is duck-typed: anything
   exposing `entity_registry` + `relationship_registry` (a real pipeline or a
   tiny `_Graph` test container with those two attrs). `sync` snapshots via
   each model's existing `to_dict()`; `load()` rebuilds real
   `Entity/Relationship` objects via existing `from_dict()` and registers them.
   This is why you use the module's own serialization — the persistence layer
   stays at the boundary and never re-implements model logic.

6. **Provenance per entity.** `provenance(entity_id, source, evidence,
   confidence)` table; `add_provenance` / `get_provenance(entity_id)`. Attach to
   entities at sync time from `metadata['provenance']`.

7. **Contradiction detection preserved + provenance-cited.** Run the existing
   `ContradictionManager.scan()` over persisted entities/relationships. Then
   annotate each `ContradictionRecord`'s sides with the provenance of the
   involved entity IDs pulled from `get_provenance`. ContradictionRecord already
   has `claim_a_source`/`claim_b_source`; populate them + a
   `metadata['provenance_sources']` list. No modification to the detector needed.

## Wiring into the module (thin)
- `__init__.py`: add the class/factory to `__all__` + imports.
- Module wrapper class: read `config.get("db_path", "data")` in `__init__`,
  build persistence with `create_persistence(None if path is None else path)`,
  expose as `self.persistence`. `None` → memory. Wrap in try/except so a
  persistence failure degrades gracefully (module still boots HEALTHY).

## Test recipe (12–18 tests → I wrote 34, all passing)
Cover: construction/backends (memory vs file vs directory), entity upsert/get/
list + type filter, get-missing→None, accept entity-object directly, dedup by
(type,id), relationship upsert/get/filter-by-from-id, provenance add/get/multi/
filter, delete-cascade, stats, round-trip across reopen (fresh connection reads
back), sync→load rebuilds graph, load populates existing graph, sync persists
embedded provenance, contradiction still reported WITH provenance sources, and
module wiring exposes `persistence`.
- Use `tmp_path` fixture; run with `-p no:cacheprovider`.
- For reopen tests, hold `db` path from the `tmp_path` fixture, open, write,
  close (`with` block), reopen a NEW `KGPersistence(db)`, assert.

## Gotchas
- A connection is reused for the life of the object → use `with self._conn:` for
  transactional writes and don't leak. Provide `close()` + context manager.
- `json.dumps(..., default=_jdefault)` for non-serializable (set/datetime/enum).
- Thread-safe via a single `threading.RLock` around all ops.
- Directory `data/` is gitignored in the enterprise repo — writing the default
  DB there won't dirty `git status`.

## Verification
```
cd "/home/hunter/Desktop/Enterprise Builder/enterprise"
python3 -m pytest modules/knowledge_graph -q -p no:cacheprovider
# 191 passed (157 original + 34 new)
```
