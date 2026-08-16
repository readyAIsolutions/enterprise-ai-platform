# Master-class persistence + A/B variant optimizer (prompt_context)

Session: upgraded `modules/prompt_context` to a persistent prompt registry + real
A/B optimizer (baseline 174 green -> 196 green, +22 tests). Pattern generalizes
to any in-memory module that needs durable state + data-driven variant selection.

## Design: SQLite-backed store that never breaks the in-memory API

The single most important trick: **add persistence as an opt-in layer, keep the
default constructor behavior identical.** Existing tests/users calling
`Module()` keep pure-in-memory behavior; only callers that pass a db path get
durability. Never change the default.

```
class PromptRegistry:
    def __init__(self, storage_path=None, db_path=None):   # NEW param only
        self._prompts = {}      # in-memory dict is still the source of truth
        if db_path is not None:
            from .persistence import PromptStore
            self._store = PromptStore(db_path)
            self._load_from_store()
```

Rules that keep it regression-free:
- `db_path=None` => memory only, `self._store is None`, no file ever written
  (tests assert `reg._store is None` to guarantee this).
- Store a **lossless full-record JSON blob** (`record.to_dict()`) as one column
  in addition to the indexed columns (template/version/status/metadata). This is
  what makes round-trip survive a reopen for nested/versioned records — a flat
  row model silently drops changelog/history/metrics. `_load_from_store()`
  reconstructs `PromptRecord.from_dict(row["record"])`.
- **Write-through on every mutation** (define/update/delete/set_status/rollback/
  record_metric each call `self._persist(pid)` after mutating the dict). Add a
  `flush()` (persist all) + `close()` (flush + close store) for lifecycle.
- Keep per-row metadata carrying the object id (e.g. `{"prompt_id": ...}`) so
  hard-delete can locate and remove the row by object id, not by display name.
- Version history in SQLite: separate append-only table with a
  `UNIQUE(name, version)`; row input via `INSERT OR IGNORE` only when the
  version actually changed (compare current stored version first).
- open/close/reopen tests over a temp dir prove durability; use
  `:memory:` (`db_path=None` / explicit in-memory) for ephemeral tests.

## A/B optimizer: real epsilon-greedy, deterministic with a seed

Not a stub — actual data-driven selection with throttle + persistence.

```
ABOptimizer(prompt, variants, epsilon=0.1, min_samples=10, seed=None, db_path=None)
```
- Per-variant stats kept in memory as `VariantStats(n, sum_score, best_score,
  last_used, created_at)`; `mean_score = sum/n`. Keep the sum, recompute mean
  (don't store the mean — accumulated rounding).
- `select_variant()`: single variant => return it; with prob `epsilon` explore
  (uniform random choice); else exploit = max mean among variants with
  `n >= min_samples`. If nothing clears the throttle, fall back to uniform
  random (bootstrapping exploration) — **never serve a statistically-meaningless
  "winner" purely on 1 sample.**
- `best_variant(min_samples=None)`: exploit-only query that returns `None` under
  throttle (used to assert the throttle in tests).
- Determinism: private `random.Random(seed)` (NOT `random.choice`/`random.random`
  globally which are seed-independent per-call).
- Persist stats through the same PromptStore: one row per variant carrying
  `{"prompt":.., "stats": st.to_dict()}`; reload on open. Tests: write N samples
  each, close, reopen, assert `stats(a).n` and mean survived.
- Tests to hit: exploits best after enough samples; explores all under
  epsilon=1.0; throttles (best_variant()=>None at low n); seed-determinism
  (same seed => same n totals, rerun idempotent); stats tracking (n/mean/best/
  last_used); persistence across reopen; auto-register on record; no-variants
  raises — but assert the STORE's NotFoundError, not a same-named error from a
  sibling module (easy import-mixup bug).

## Export surface
- `from .persistence import (PromptStore, PromptStoreError,
  PromptNotFoundError as StorePromptNotFoundError, VariantStats, ABOptimizer)`
  and add each to `__all__`. Alias the store's NotFound so it doesn't collide
  with a different module's `PromptNotFoundError`.

## Pitfalls hit
1. Sibling/swarm agents edit the same repo concurrently — confine your diffs to
   your module; verify with a `git status --short` filtered to your path and
   report "I did NOT touch <other files>" explicitly.
2. Assert the correct exception class in tests (store's NotFound vs registry's).
3. Run the WHOLE module suite (not just new tests) at the end to prove no
   regression: baseline count -> total after.
