# Security Module Waves — graft OSS security tooling as stdlib-only kernel modules

How to expand the ENI Enterprise Platform with many security modules fast, by
rebuilding open-source security tooling "better than the original" (local-first,
offline, zero deps) and landing them as first-class kernel modules. Proven across
two waves (+10 modules, +~500 tests).

## The winning pattern (per wave)

1. **Pick from the security roadmap** (garak / deepeval / langfuse / guardrails /
   OWASP LLM Top 10 / NIST AI RMF / MITRE ATLAS / STRIDE). Each is a real, verified
   OSS project; graft means implementing a *stdlib-only offline* version, NOT
   vendoring it.
2. **Fan out one subagent per module** via `delegate_task` batch. Give each a
   RAZOR spec (from `eni-swarm-content-gen` discipline) containing ALL of:
   - exact file paths (modules/<name>/<name>.py + __init__.py + tests/)
   - the exact Module base contract (see below)
   - exact class/function names + signatures + I/O contract
   - HARD constraint: **STDLIB-ONLY** (dataclasses, enum, threading, re, json,
     hashlib, uuid, collections, statistics, typing — never numpy/pandas/requests)
   - "write ~N+ pytest tests; all must pass with `python3 -m pytest
     modules/<name>/tests -q` from repo root"
   - the CRITICAL final-block requirement (the swarm-reasoning rule)
3. **Verify each subagent's self-report yourself.** Subagents say "all tests
   pass" — re-run the suite independently. Every wave I confirmed the exact count.
4. **Register each in config.yaml** (enabled/priority/required/config) and run a
   kernel-boot probe: `await m.initialize()` then assert `m.status` == HEALTHY for
   every new module. Also assert the full platform suite count rose by the exact
   number of new tests.
5. **Write a STATUS doc** with a real PASS/FAIL board (per-module test counts,
   full-suite total, config module count, boot HEALTHY count) + an honest
   UNVALIDATED section.

## The module base contract (what every subagent must match)

Put this verbatim in every razor spec — it's the thing that prevents
incompatible modules:

```python
from enterprise.platform_kernel import EventBus, HealthStatus, Module, module
@module(name="<name>", version="1.0.0")
class <Name>Module(Module):
    async def initialize(self): ...        # set self._status = HealthStatus.HEALTHY
    async def health_check(self) -> HealthStatus: ...
    async def shutdown(self): ...
    def set_event_bus(self, event_bus: EventBus): ...
# base already gives self._status (.value to stringify), self._config, self.name,
# self.version, self.module_id
```

Test import convention: `sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
` then `from enterprise.modules.<name>.<name> import (...)`.

## The 6-module security wave (reference blueprint, all landed)

| module | OSS source | core capability |
|--------|-----------|-----------------|
| `llmops_trace` | langfuse | local Trace/Span nesting, p50/p95/p99 latency, error rate, cost est, tree, JSON/JSONL export + file backend, size-cap eviction |
| `vuln_scanner` | garak | 7 offline attack probes (prompt injection, jailbreak, PII leak, prompt extraction, toxicity, data-exfil, refusal echo) → risk score/level/stop_rate, rescorer |
| `guardrails` | guardrails-ai | validators + validate/refix/reask loop: NoPII, NoToxic, JSONSchema, Profanity, Length, Regex, NoPromptInjection; on_fail filter/raise/fix/refix |
| `compliance` | OWASP LLM Top 10 + NIST AI RMF + MITRE ATLAS | 18 controls across 3 frameworks → coverage %, risk, PASS/FAIL, gap analysis, report |
| `secret_rotation` | credential hygiene | hash-only storage (sha256, raw never kept), rotation policies, expiry/due (injectable clock), breach revocation, due report |
| `threat_model` | MITRE ATLAS / STRIDE | 17-threat catalogue, risk=likelihood×impact, severity, STRIDE mapper per asset, mitigation coverage |

Earlier wave: `a2a` (Google A2A protocol), `eval_gate` (deepeval-style offline
metrics), `agent_graph` (langgraph-style stateful graphs + checkpoints),
`skill_factory` markdown-skills-standard import.

## Gotchas hit while building these

- **PII/profanity must pass the wordlist check with real inflections** — word
  boundaries mean "shit" doesn't catch "shitty"; add inflected forms explicitly.
- **Module `health_check`/`initialize` are `async`** — tests must
  `asyncio.run(...)` and compare the returned status, not call synchronously.
- **Injectable clock for time-based modules** (secret_rotation expiry/due) — pass
  `now` as absolute epoch, injectable for deterministic tests; don't call
  `time.time()` inline everywhere.
- **Histogram/percentile assertions need tolerance** — p95/p99 or coverage
  (2/3 = 0.6667) — use `pytest.approx` / abs tolerance, not exact equality.
- **Entry-point resolution in graph engines**: supervisor graphs add edges from a
  START marker → treat edges originating from START as entry edges, else
  "no entry point" error.
- **Empty-store falsiness**: if a store defines `__len__`, `store or Default()`
  silently discards a passed empty store. Use `store if store is not None`.
- **Subagent self-reports are NOT facts** — the one full-suite "failure" a
  subagent blamed on "pre-existing flaky module" was in ANOTHER module the same
  wave built; re-running independently confirmed it green. Always re-run yourself.
