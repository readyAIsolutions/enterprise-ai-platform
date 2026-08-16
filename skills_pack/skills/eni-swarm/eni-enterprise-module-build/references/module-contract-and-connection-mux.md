# ENI module contract + @module dedupe + connection-mux pattern

Session: rebuilt/upgraded `swarm_network` to master class — deduped a confusing
double `@module` registration, added factory function, and built a real
connection-multiplexer with scoring + automatic fallback (52 tests green).

## 1. The module CONTRACT every ENI module must satisfy

Every capability module in `~/Desktop/Enterprise Builder/enterprise/modules/<name>/`
is expected to expose a `<module>.<name>` factory in `__init__.py`:

    def create_<name>_module(config: Optional[Dict[str, Any]] = None) -> <Name>Module:
        return <Name>Module(config=config or {})

Check `modules/a2a/__init__.py` and `modules/agent_coordination/__init__.py` for the
canonical form. A module may ship with only a `create_<x>_facade()` helper and be
MISSING the `create_<name>_module()` factory (found this on `secret_rotation`, which
had `create_rotation_facade` but no `create_secret_rotation_module`) — the contract
factory is the required entry point, add it when upgrading. The `swarm_network` module was MISSING this factory — adding it was
required to satisfy the module contract, and it belongs in the SKILL checklist for any
"add/upgrade a module" task. Run a quick grep across modules for the pattern before
declaring a module conformant:

    grep -rn "def create_.*_module" modules/*/__init__.py

## 2. The @module registry quirk: decorator registers by NAME key

`platform_kernel.module()` writes `_MODULE_REGISTRY[mod_name] = cls` (a dict keyed by
module name). Registration is idempotent-by-key, so a genuine double `@module`
decorator does NOT create duplicate registry entries — the later one overwrites.
The real risk is CONFUSION / doc drift:

- A second `@module(...)` that lives inside the module docstring (triple-quoted) is
  cosmetic, not executable — it looks like a duplicate but registers nothing.
- If a task says "dedupe the double @module registration", the fix is: keep exactly
  ONE executable `@module(name=...)` decorator on the module class, and strip/rewrite
  any docstring copy so `grep -c "@module(" __init__.py` == 1.

### Verify dedupe properly
- Source-level: `grep "@module("` — exactly ONE line.
- Registry-level: import `from enterprise.platform_kernel import _MODULE_REGISTRY`, then
  `[k for k in _MODULE_REGISTRY if k == "<name>"]` — exactly one key, whose value is the
  module class (`assertIs(reg[k], <Name>Module)`).
- Add a unit test asserting BOTH (single decorator line in source + single registry key).
- Do NOT rely on `_MODULE_REGISTRY` count alone to prove a duplicate existed — since it
  is keyed, a real duplicate would have already been collapsed.

## 3. The `enterprise` package IMPORT QUIRK (bit me this session)

`import enterprise` FAILS from the repo root cwd with plain `python3 -c "import enterprise"`,
even though pytest green. Reason: the `enterprise` package is NOT resolved as a subdir of
cwd — the root `conftest.py` inserts the REPO PARENT on sys.path (and aliases under
`enterprise` when the checkout dir is named differently). So:
- ALWAYS run imports/tests from the repo ROOT (`cd ".../enterprise"`) and let conftest
  fix paths (that's why `pytest` works but bare `python3 -c "import enterprise"` doesn't).
- For a standalone import one-liner, insert the PARENT dir, not cwd:
  `sys.path.insert(0, "/home/hunter/Desktop/Enterprise Builder")` (the parent), then import.
- This is a repo convention, not a defect — don't treat it as "import is broken."

## 4. Connection-multiplexing pattern (real scoring + auto fallback, no stubs)

Reusable stdlib-only design for "connection multiplexer / load balancer / failover"
tasks. Split into a dedicated `<name>/mux.py` and export from `__init__.py` __all__:

- **Link** dataclass: `id, type, name, metric, up, last_test`.
  `metric` = intrinsic priority tie-break used AFTER score (lower preferred).
- **ConnectionScorer**: weighted 0-100 composite over INJECTABLE signals —
  `signal` (0-1), `bandwidth` (0-1), `latency_ms` (fraction of a budget),
  `reliability` (0-1). Weights auto-normalised to sum 1. Each component clamped 0-100.
  Injectable signals are the key to deterministic testing (no real hardware).
- **LinkManager**: register/register_new/get/unregister, `mark_up/mark_down`,
  `test/test_all` (with injectable `probe_fn`), `score_link`, and `best_link()` —
  higher score wins, LOWER metric breaks ties, down links excluded, None if all down.
- **Muxer.route(data, prefer=None, task=None)**: resolve candidate order deterministically
  (prefer first, then score desc, then metric asc); on send exception mark that link down,
  auto-retry next-best; accumulate per-link {ok, fail, fallback} + global
  total_fallbacks/total_success/total_failures. Raise RuntimeError if all fail / none
  configured. Support a `task=` kwarg forwarded to the send fn.
- **select_route**: deterministic, side-effect-free fallback for tests/callers — UP only,
  prefer wins ties, then score, then metric, then alphabetical id for full determinism.

### Test latency pitfall (bit me)
- Latency scoring uses a budget; at exactly half the budget the score is exactly 50.0.
  Don't write `assertGreater(score_latency(<half>), 50)` — half budget == 50.0 exactly.
  Use a value strictly below half (e.g. 40% budget) for `>` assertions.

### Workflow that keeps it green (reuse from integrity reference)
1. Baseline the module suite first: `pytest modules/<mod> -q -p no:cacheprovider`.
2. Add mux.py + a test file covering: dedupe, scoring, best_link, route+fallback,
   stats, up/down transitions, lifecycle, deterministic select_route.
3. Re-run the WHOLE module (not just new tests) — no regression.
4. Report real PASS counts: module suite = N passed (X new + Y legacy).
