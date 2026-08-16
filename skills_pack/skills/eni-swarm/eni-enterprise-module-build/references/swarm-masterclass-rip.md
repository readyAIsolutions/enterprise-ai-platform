# Swarm Rip-and-Rebuild: Master-Class Module Workflow

Used to rebuild 6 enterprise modules in one parallel swarm wave (guardrails, mcp_tools,
a2a, semantic_memory, model_security, gateway) — each ripped from a proven permissive
license (MIT/Apache-2.0) OSS pattern and rebuilt to "master class".

## Module contract (must satisfy, or the module won't boot)

- A module = `modules/<name>/` with an `__init__.py` exposing `__version__` and a
  `@module(name, version, config_defaults)`-decorated subclass of `platform_kernel.Module`
  implementing `async initialize() / health_check()->HealthStatus / shutdown()`.
- Also expose a `create_<name>_module(config)` factory.
- Config is wired under the top-level `modules:` map in `config.yaml` (enabled/priority/
  required/startup_timeout_sec/health_check_interval_sec/config).
- Verify registration: `ModuleRegistry().discover()` then check
  `record.module_class is not None` for the new module, and boot
  `PlatformOS.create_platform() -> start()`, confirm status HEALTHY.

## The master-class rules (non-negotiable)

- **Preserve ALL existing public API and pass ALL existing tests.** Rebuild ADDITIVELY:
  keep every export and legacy behavior, layer the new capability + its tests on top.
  Never delete a public name; never weaken an existing assertion.
- **No stubs, no fake data, honest health.** A real health probe must actually exercise
  a representative component and return UNHEALTHY/DEGRADED when it's broken. Hunt down
  known stubs (`return ""`, `NotImplementedError`, `# placeholder`) and eliminate them.
- **stdlib-only unless the module already uses external deps.** Do not add dependencies.
- **Every module becomes an extension point** (plugin registry, registry of validators/
  tools/probes/detectors), not a closed implementation.

## Proven rip targets (all permissive, stdlib-reimplementable)

| Module | Rip target (license) | Build |
|--------|----------------------|-------|
| guardrails | Guardrails-AI validator registry (Apache-2.0) | `@register_validator(name,data_type)`, PassResult/FailResult + on_fail fix/block/raise |
| mcp_tools | FastMCP `@tool` decorator (Apache-2.0) | signature-introspection JSON-Schema, sync+async dispatch, Transport ABC |
| a2a | Google A2A durable task protocol | SQLite TaskStore WAL, vertical TaskState transitions, AgentCard discovery, TaskRouter, in-memory transport |
| semantic_memory | Zep temporal recall + mem0 ranking | since/until/time_bucket search, recall_since, ranking, consolidate, migration-safe SQL columns |
| model_security | Garak probe/detector split (Apache-2.0) | Probe(generator)/Detector(judge) ABCs, registry, SecurityScanner -> ScanReport(stop_rate) |
| gateway | OpenAI handoff + resilient retry | DeliveryPolicy/Receipt, send_with_retry exponential backoff, GatewayRouter fallback handoff, Outbox |

## IMPORTANT PITFALL: ENI compression hides large file reads

When reading enterprise files, large `read_file`/terminal outputs come back wrapped as an
"ENI-compressed carrier" (PNG + XZ) showing only a lossy head/tail — you cannot see the
full source through it. This hits EVERY subagent and blocks full-file understanding.
- **Workaround:** read in small ~50-60 line slices per call (stays under the compression
  threshold) or use `grep`/`sed -n 'a,b'`/`awk` to pull exact signatures. Compile the
  result with `python3 -m pytest`/`ast.parse` to prove the on-disk file is intact.
- This is a display/tooling artifact, NOT a repo defect — do not "fix" the files because
  of it, and do not conclude the files are corrupt. The on-disk source is fine.

## Running the wave

- Fan out one worker per module (they touch disjoint dirs -> no file collisions), each
  self-contained: read module -> preserve API -> build + tests -> `pytest modules/<name>`
  green. Require a CRITICAL reasoning block in each worker's summary.
- Verify independently after: full `pytest -q -p no:cacheprovider` (no regressions), and
  boot all modules HEALTHY through the real kernel.
- Add/update a `docs/STATUS_*.md` with a PASS/FAIL board + UNVALIDATED section.
