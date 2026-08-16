# Massive Parallel Swarm-MasterClass Wave + Cross-Module Integration Discipline

Technique proven across three full-fleet rebuilds of ENI enterprise (~/Desktop/Enterprise
Builder/enterprise): master-class EVERY module in a handful of parallel swarm waves, then
catch the contract drift between them. This is the pattern LO calls "use swarm... rip and
rebuild... every module master class" and "do all modules full massive swarm."

## Fan-out recipe (swarm sizing + no-collision)

- **One worker per module, never two workers touching the same file.** List every module
  dir first, group the ones already done, and fan out one `delegate_task` with N tasks —
  each task owns exactly ONE `modules/<name>/` dir (plus its own `tests/` + `__init__.py`).
- **Split overlapping modules into distinct home files.** If two legitimate improvements
  target one module (e.g. `innovation_rd` experiments/stats vs its integrity ledger), give
  each worker its OWN new file (`experiments.py` vs `integrity_ledger.py`) and explicitly
  forbid one from editing the other's file. They land cleanly without a merge.
- **Batch by real hole, not by count.** Before a wave, grep for the actual weaknesses:
  `NotImplementedError`, `placeholder`, `# stub`, `TODO: implement`, `return ""` (stub
  recipients), modules with ZERO tests. Confirm which modules are already mastered and
  skip them.
- **Do NOT fan out at max concurrency blindly** — a 28-task single call works but its
  result payload is huge; keep each task's goal self-contained and require a one-line
  PASS/FAIL + count in the summary.

## Fixed worker instructions every subagent MUST get

1. **Preserve the module's legacy public API + all existing tests.** The whole platform
   passes at baseline; a worker that breaks a sibling's test poisons the fleet. Say it
   explicitly: "preserve ALL existing exports and pass ALL existing tests."
2. Give the exact module contract: `modules/<name>/__init__.py` with `__version__` + a
   `@module(name,version,config_defaults)`-decorated `Module` subclass (async
   `initialize/health_check/shutdown`) + `create_<name>_module(config)`. Reference
   `modules/model_security` or `modules/eval_gate` as the shape to copy.
3. "Master class = real, tested, no stubs, honest health." Name this bar directly.
4. Hermetic + offline-tested: inject adapters/clocks/sleeps/runners for tests; use
   ephemeral ports (port 0) for any HTTP; never hit the network in CI.
5. Exact run + report: `cd repo && python3 -m pytest modules/<name> -q -p no:cacheprovider`,
   give real PASS/FAIL + count.
6. **CRITICAL: end the summary with a CRITICAL block** (what understood / pattern ripped /
   built / real numbers / issues) — feeds the reasoning visualizer.

## The cross-module integration suite (the #1 payoff)

After modules are master-classed in ISOLATION, parts that were never wired together
silently drift. Build ONE integration test dir (`tests/integration/`) that calls each
module's REAL facade end-to-end (offline via each module's injectable offline adapter),
asserting EXACT return shapes across boundaries. This caught 3 real contract-drift bugs
in the fleet and would otherwise surface as runtime failures after auto-wiring:

- `agent_core.QueryResult.messages[0].role` is `"user"` not prepended `"system"` (no
  default system prompt unless `system_prompt` configured).
- `OpenAICompatibleBackend` passes `config.model or "gpt-4o"` to the provider, NOT the
  routed model name — set `QueryConfig(model=...)` or the mock records `gpt-4o`.
- `universal_score.DimensionResult.to_dict()` emits `{"dimension,score,sub_signals:
  [{key,name,score,evidence}]}` — not `{signals,metric,passing}`.

**Lesson:** assert the ACTUAL facade signatures (read them, don't predict them). The
integration suite's whole job is to catch exactly this. Wire flows like
`model_router→agent_core→eval_gate→universal_score` and the security-evidence chain
(`vault↔rate-limit↔compliance`), asserting shapes at each hop.

## The KB-driven improvement loop (how to pick the next wave)

The enterprise repo's own `docs/STATUS_*.md` files are the best source of improvement
ideas — each carries an **UNVALIDATED** section and a **"Next push candidates"** list.
To find the next wave: mine `~/.eni/kb/` (patterns.db/skills.db) + the repo `docs/*.md`
with one or two read-only subagents, have them converge on the TOP gaps, then size the
swarm to those. Two independent miners converging on the same top-6 is a strong signal
the ideas are real, not single-agent noise.

## Independent verification — never trust the swarm's self-report

Subagents return self-reported "all green." ALWAYS re-run the full suite + boot yourself:

```bash
cd ~/Desktop/Enterprise\ Builder/enterprise
python3 -m pytest -q -p no:cacheprovider          # whole fleet
python3 -c "import sys; sys.path.insert(0,'/home/hunter/Desktop/Enterprise Builder'); import asyncio; from enterprise import platform_kernel as pk; asyncio.run((lambda os: (os.start(), print(len([r.name for r in os.module_registry.list_modules() if r.instance and r.instance.status.value=='healthy']),'healthy'), os.shutdown()))(pk.create_platform()))"
```

Confirm module COUNT went up and every module reports healthy. A skipped smoke test is
fine (env-gated); a FAIL is not — fix or skip it before committing.

## Build-tracking convention

Commit each wave + a `docs/STATUS_DEMIURGE_<TOPIC>.md` with: PASS/FAIL evidence board,
"what adds R / what to drop", an explicit UNVALIDATED section, and verification commands.
This is what makes the KB-driven loop possible next time.
