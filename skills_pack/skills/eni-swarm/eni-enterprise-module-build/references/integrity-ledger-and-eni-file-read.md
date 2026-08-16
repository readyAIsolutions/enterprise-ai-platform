# Master-class integrity subsystem + reading the ENI repo's compressed files

Session: rebuilt the `innovation_rd` module's integrity layer into a real,
tamper-evident integrity ledger + reproducible-run fingerprinting (baseline 116
green -> 146 green, +30 tests). Two durable takeaways.

## 1. Reading files in ~/Desktop/Enterprise Builder/enterprise (ENI compression)

Large `read_file` calls in this repo come back as `ENI-COMPRESSED ... carrier=...`
blobs instead of real text. This is NOT a tool failure — it is an environment
compression layer. It wastes calls and hides content if you don't account for it.

- **Fix pattern (read_file):** read in SMALL chunks via `offset`/`limit`
  (~60 lines per call). Small reads return real content; large reads trip the
  compressor and come back as an opaque carrier blob.
- **Fix pattern (terminal):** `terminal cat`/`sed` of a file over ~100-120 lines
  ALSO trips the compressor. So chunk with `sed -n 'A,Bp' file.py` keeping each
  slice <= ~80-110 lines — that reliably returns real text and is the fastest way
  to read these files without `read_file` offsets.
- The PNG-carrier decompress path (`workers.compression_worker.pxpipe_decode` +
  `paq8_decompress`) is UNRELIABLE for these carriers (returns
  "cannot load this image" / tiny garbage). Don't burn time decoding carriers —
  just re-read the source in small chunks.ressor.
- Threshold varies by file (~13KB and above tends to compress; ~1.7KB test files
  came through fine). When you hit a compressed blob, shrink the window and re-read.
- **BEST technique — extract the API via `terminal` + Python `ast` instead of
  fighting the compressor.** Terminal/stdout is NOT compressed, so dump the real
  structure in 1-2 calls: walk the AST and print every class + method signature,
  module-level constants, and dataclass fields. This gives the exact public API
  (method names, arg order, return shapes) needed to preserve it, without
  chunked-reading slogs. Example one-liner shape (run from the module dir):
  `python3 - <<'EOF'` reading `ast.parse(open(fn).read())` and printing
  `ClassDef`/`FunctionDef` names + `ast.get_source_segment(src, node)[:N]` for
  the few classes you depend on (dataclass fields via source not type stubs). Also
  `grep`/`search` through terminal works on real bytes for constants and imports.
- Verify the dataclass field lists you depend on by reading the narrow slice that
  contains only those fields (e.g. `offset=44, limit=40` for an `@dataclass` body).
- Prefer reading `git status --short` to confirm exactly which files you added /
  changed instead of assuming — the worker-separation rule below depends on it.

## 2. Building a tamper-evident integrity ledger (real, no stubs)

A proven pattern for "add a master-class integrity subsystem" tasks in this
codebase. Stdlib-only: `hashlib + sqlite3 + json + dataclasses`.

- **RunFingerprint (deterministic identity):** sha256 over
  `{inputs, code_version, params, seed, env}`. Key to determinism is CANONICAL
  serialization: sort dict keys recursively, Enum->`.value`, datetime->isoformat,
  sets sorted, lists kept ordered. Two runs with the same logical inputs must hash
  identical regardless of insertion order.
- **Env filtering:** drop volatile env keys (time/pid/path/random/hostname/term +
  any `timestamp`-like) so fingerprints survive machine differences.
- **Hash-chained SQLite ledger:** table stores
  `{seq, run_id, fingerprint, actor, action, isolation, recorded_at, prev_hash, record_hash}`.
  Each `record_hash = sha256(content + prev_hash)`; first record links to a fixed
  `GENESIS_HASH = "0"*64`. Append-only: expose only `append()`; no public mutation.
- **Verifier detects 3 tamper classes:** (a) modification = stored `record_hash`
  != recomputed hash; (b) insertion = foreign record with wrong `prev_hash`/hash;
  (c) deletion = non-contiguous `seq` gaps. Return a result object carrying
  `tampered_seq / broken_links / missing_seq` so callers can say WHAT was tampered.
- **Honest isolation hook:** store an `isolation` bool flag IN the chained record
  (via a `record_isolation_run()` helper) so sandbox usage is provable from the chain.

## 3. Additive module upgrade — new submodule, preserve all API + tests

Upgrading an existing module to "master class" (risk register, ledger, planner,
scheduler, etc.) follows a safe additive recipe that never regresses the existing
suite:

- **New file lives beside the module** (e.g. `threat_model/risk.py`),
  stdlib-only, self-contained, not importing the sibling file it extends. This
  avoids circular imports and keeps it independently testable.
- **Wire it in additively:** import in the module's `__init__.py` and ADD the new
  symbols to `__all__` (don't reorder/remove existing ones); mount an instance on
  the facade constructor (e.g. `self.risk = ThreatAssessment()`) or the module's
  `initialize()`. Never mutate existing method signatures or return shapes.
- **Two imports may coexist:** `__init__.py` does `from .risk import ...` then
  `from .threat_model import ...`, and `threat_model.py` can `from .risk import
  ThreatAssessment` — safe because `risk.py` imports nothing from the sibling.
- **Splitting imports across two files:** when the source file grows a new
  relative import, keep the shebang + module docstring as lines 1-2 (don't prepend
  the import above them), and place the relative import after the third-party
  block, before the logger.
- **Write the new module's tests separately** (`tests/test_risk.py`) with its own
  `sys.path.insert(...parents[3])`, then run the WHOLE module not just the new
  file, and report baseline+new counts.

Domain pattern examples confirmed in this class of task: a **risk register**
(SQLite CRUD + status lifecycle open->mitigated->closed + severity/status/category
filtering + file-path persistence), a **mitigation planner** (STRIDE category ->
minimum viable controls + per-risk proposed/applied/verified tracking + coverage
fraction), and a **CVSS-like severity score** (weighted 0-10 formula; document the
weights in the docstring: impact 60% + exploitability 40% where exploitability =
likelihood x attack-vector ease x privilege-required ease).

## Pitfalls that bit (and their fixes)

- **`enterprise` is a pytest conftest-time module alias, NOT a real importable
  package.** The root `conftest.py` aliases the repo root as `enterprise` via
  `importlib.util.spec_from_file_location` (so it works whether the checkout dir
  is named `enterprise` or `enterprise-ai-platform`). Consequence: `pytest` from
  repo root resolves `import enterprise.*` fine, but a plain terminal
  `python3 -c "import enterprise.modules.X"` from repo cwd FAILS with
  `ModuleNotFoundError: No module named 'enterprise'` even with `.` on `sys.path`.
  This is NOT a code problem. To smoke-check outside pytest, replicate the conftest
  alias (load the root `__init__.py` under module name `enterprise` with
  `submodule_search_locations=[repo_root]`) or just trust `pytest modules/<mod>`.
  Don't burn time debugging why `import` fails in `-c` / `python -i` — use pytest.

- **sqlite UNIQUE collision when simulating insert-tamper:** to inject a "foreign"
  record in a test, pick a `seq` that does not collide with real rows (e.g. append
  2 records then insert at `seq=3`, not `seq=2`). Otherwise you get
  `sqlite3.IntegrityError: UNIQUE constraint failed`.
- **Reproducibility assertion flake:** when comparing a helper-produced digest
  against a hand-built one, every component must match EXACTLY (e.g. `"mnist-v1"`
  vs `"mnist"` silently makes them unequal). Copy the exact strings.
- **Pyright strict on `**kwargs` helpers:** type helper kwargs as `**overrides: Any`
  and unpack via `.get()` instead of splatting straight into a typed call.
- **Worker separation:** when a task says "another worker owns experiments.py /
  test_experiments.py", confirm via `git status --short` that you ONLY added your
  new files before finishing, and state that confirmation in the summary.

## Workflow that keeps it green

1. Run the existing module suite FIRST (`pytest modules/<mod> -q -p no:cacheprovider`)
   to capture the baseline count before any edits.
2. Add new file(s) + new test file; keep `:memory:` or tempfile for ledger tests.
3. Re-run the WHOLE module (not just new tests) to prove no regression.
4. Report real numbers: baseline + new, total passed/failed, and the explicit
   "I did NOT touch <other worker's files>" confirmation.
