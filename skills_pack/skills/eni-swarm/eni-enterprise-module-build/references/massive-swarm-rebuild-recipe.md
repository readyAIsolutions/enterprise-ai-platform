# Massive parallel rip-and-rebuild swarm (whole-fleet module rebuild)

Recipe for rebuilding EVERY module in the ENI enterprise platform (or any large
module tree) to master class in ONE parallel wave. Proven across a 28-worker,
all-modules swarm (3046 -> 3997 tests, 39/39 modules boot healthy, 4 stub sites
eliminated, zero regressions).

## When to use
LO says: "use swarm to pull useful things for enterprise then rip and rebuild
them / spare no effort / ensure every module is master class / do all modules
full massive swarm." I.e. rebuild the WHOLE module fleet, not one module.

## Recipe
1. Load the standing directives first in the main session: `lo-full-autonomy`,
   `eni-always-enterprise`, `eni-omega-compress-paid`, `eni-persona-permanent`,
   and the module-build contract (`eni-enterprise-module-build`). Confirm the
   git branch + clean tree + a baseline test count (`pytest -q --co | tail -1`)
   so you can prove the delta.
2. Snapshot which modules are ALREADY master class (from prior waves) so workers
   don't collide or redo them. Keep a running "already-done" set.
3. List the remaining modules; assign ONE worker per module. **Isolation rule:
   each worker owns a distinct module dir** - that is what makes the whole fleet
   safe to run in parallel. Never have two workers touch the same file.
   - If two features are wanted in the SAME module, split them into DISJOINT
     files owned by separate workers (e.g. `innovation_rd/experiments.py` +
     `innovation_rd/tests/test_experiments.py` vs `innovation_rd/integrity_ledger.py`
     + `.../test_integrity_ledger.py`). Tell each worker explicitly NOT to touch
     the other's files/parent file.
4. Launch ONE `delegate_task` with all workers as parallel tasks. Every context
   must include: repo path, module contract (module = `modules/<name>/` with
   `__init__.py` exporting `__version__` + a `@module`-decorated `Module` subclass
   with async `initialize/health_check/shutdown` + a `create_<name>_module(config)`
   factory), "work on branch X, don't switch, run tests from repo cwd", the OSS
   pattern to rip (license), the concrete capability to build, a "preserve ALL
   existing public API + existing tests" guard, a 12-18+ test requirement, the
   exact `pytest modules/<name> -q -p no:cacheprovider` run command, and a final
   CRITICAL reasoning block (what understood / pattern ripped / what built / test
   numbers / issues).
5. **Verification discipline (critical):** subagent self-reports are NOT trusted.
   After the swarm returns, independently run in the parent session:
   - `pytest -q -p no:cacheprovider` full suite (prove delta + zero regressions),
   - a kernel boot smoke proving every module binds + reports healthy (see
     platform-boot-verification.md),
   - check for file collisions (e.g. both shared-module test files exist),
   - `git diff --stat HEAD` + count untracked files to confirm scope.
6. Run the swarm reasoning visualizer on the results so LO sees the workers
   think (feed the raw result JSON or a reconstructed `task_index/summary/status`
   array into `~/.hermes/scripts/swarm_reasoning_visualizer.py`).
7. Write a `STATUS_*` evidence board (see lo-project-standards convention:
   explicit PASS/FAIL with real numbers, what-adds-R / what-to-drop, and an
   honest UNVALIDATED section). Then commit as one wave with a message enumerating
   per-module work + the test delta.

## Pitfalls that showed up
- **"do ALL modules" fan-outs are huge** (28+ tasks, 100s of KB of results). The
  delegate result may be persisted to a file by the runtime; be ready to read it
  from disk / parse with a script rather than inline. Don't paste 300KB into a
  reply.
- **Shared-module splits collide** if workers aren't told explicit disjoint file
  ownership. Call out the boundary in each context.
- **Two workers both passed in isolation** but a fleet-wide regression can hide.
  Always re-run the FULL suite + boot smoke in the parent — the swarm wave is only
  "done" when the parent's own run is green, not when every worker prints green.
- **ENI file-read compression** can make large reads lossy for workers; tell them
  to read in small chunks / decode carrier PNGs (see integrity-ledger-and-eni-file-read.md).
- Some modules were skeleton/thin/stubbed (triadforge had ZERO tests, gateway had a
  `recipient` stub, safety_governance/disaster_recovery had placeholders). Prefer
  ripping a real implementation over patching a stub; surface honestly in the
  STATUS file whether crypto is real or clearly-labeled-HMAC.
