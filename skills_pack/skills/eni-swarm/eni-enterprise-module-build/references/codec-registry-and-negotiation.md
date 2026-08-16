# Pluggable codec registry + ratio negotiation (master-class pattern)

Session: upgraded `modules/compression_bridge/` to master class — added a pure-stdlib
(`lzma`/`gzip`/`bz2`/`json`) codec layer with an ABC, a pluggable registry, and
size-based ratio negotiation, wired into the existing bridge **without** breaking any
of its 64 legacy engine tests. Final: 82 passed (64 legacy + 18 new codec tests),
exactly on the task's "write 12-18 tests" count.

## Design pattern (reuse for any pluggable-codec / negotiation layer)

### 1. Codec ABC
Every codec implements `encode`/`decode`/`ratio`/`name`/`mime` (plus optional
`compress`/`decompress` aliases to mirror the host's vocabulary). Keep the layer
PURE STDLIB so it can be imported/tested in isolation with zero dependency on the
heavy core engine — this also makes standalone verification trivial.

### 2. Registry
`register_codec` (accepts instance OR class — instantiate class form), `get`
(unknown → `KeyError`), `list` (sorted by name for determinism), `__len__`/`__contains__`.
Duplicate name → `ValueError`. Default registry auto-registers built-ins.

### 3. Size-based `best_codec` negotiation
- Run every codec over a **bounded sample** (`SAMPLE_BYTES ~ 8192`) → O(1) memory and
  fast even for huge payloads.
- Pick the codec with the **highest ratio** = `original_size / encoded_size` (i.e.
  smallest encoded size).
- **Deterministic tie-break by name**: iterate `list()` (already name-sorted) and use
  a strict `>` comparison, so ties are won by the lexicographically-smallest name and
  the result is reproducible across fresh registries.
- **Type-tolerant selection**: wrap each `ratio(sample)` in try/except and skip any
  codec that raises on the payload type. Opaque bytes → binary codecs; structured
  payloads are compressible as JSON text; `JsonCodec` becomes the type-preserving
  fallback.

### 4. NOOP codec = incompressibility floor
`NOOPCodec` returns the input unchanged with ratio exactly `1.0`. For random /
incompressible data every real compressor expands (ratio < 1.0), so NOOP legitimately
wins — the system degrades gracefully instead of growing the payload.

### 5. `negotiate_ratio(payload)` -> dict
`{codec, mime, ratio, original_size, compressed_size, saved_bytes, lossless}`.
`saved_bytes == original_size - compressed_size`.

### 6. Backward-compatible bridge integration (CRITICAL)
Add an **optional kwarg** (`codec: str | None = None`) to the existing method. When it
is `None` (the default) the method routes to the ORIGINAL engine path untouched —
this is what keeps all legacy tests green. When a codec name (or `"auto"`) is passed,
route to the new registry path and return a **drop-in result object** shaped exactly
like the engine's result (same fields: success/ratio/compressed_size/algorithm_used/
metadata), so callers can't tell the paths apart. Also expose `codec_registry` property,
`select_codec`, and a convenience `compress_best()`.

## Pitfalls (hit this session)
- **Filename `codecs.py` collides with Python's stdlib `codecs` module.** A bare
  top-level `import codecs` resolves to the stdlib module (already in sys.modules), so
  `codecs.negotiate_ratio` fails with AttributeError. ALWAYS import it as part of the
  package: `from compression_bridge import codecs`, never bare `import codecs`.
- **Size-negotiation for a structured dict picks `gzip`, not `json`** — JSON text is
  highly compressible, so a binary codec beats JsonCodec's raw `json.dumps` on pure
  size. That is CORRECT size-based behavior; don't assert "json wins for dict". Assert
  "best_codec(dict) is not noop" and test JsonCodec's dict round-trip separately (it is
  the type-preserving fallback, not the size winner).
- **Exact test-count targets**: when a task says "write 12-18 tests", consume it as a
  guided range. Parametrized tests expand the collected count fast — to land in range,
  use loops-within-a-single-test for per-codec round-trips instead of pytest
  parametrize. Report the actual function count and confirm it's in range.

## Green workflow (unchanged, reuse)
1. Baseline the module suite first: `pytest modules/<mod> -q -p no:cacheprovider`.
2. Add `codecs.py` + `tests/test_codecs.py`, wire the bridge, add the missing
   `create_<name>_module(config)` factory + exports if absent.
3. Re-run the WHOLE module (not just new tests) — no regression.
4. Report real PASS counts: module suite = N passed (X new + Y legacy).
