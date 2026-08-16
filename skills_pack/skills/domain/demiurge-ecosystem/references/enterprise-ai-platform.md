# ENI Enterprise AI Platform — architecture & module-building guide

Location: `~/Desktop/Enterprise Builder/enterprise/`
GitHub: `readyAIsolutions/enterprise-ai-platform` via SSH `github.com-enterprise`
(`main` is PROTECTED → work on a feature branch + PR).
A ~91K-line Python monorepo (~38 modules). This is the ENI "enterprise AI operating
system" — a modular, self-validating platform with an agentic kernel, swarm
orchestration, free-model routing, and a security/memory/observability module stack.

## Core = platform_kernel.py (the one kernel that matters)

- `Module(abc.ABC)` — a module is a subclass with `async initialize()`,
  `async health_check() -> HealthStatus`, `async shutdown()`.
- `@module(name, version, config_defaults)` decorator registers the class into a
  global `_MODULE_REGISTRY`.
- `ModuleRegistry.discover()` scans `modules/<name>/__init__.py`, creates a
  `ModuleRecord`, and `initialize_all()` instantiates enabled records in priority
  order then awaits `initialize()` under a per-module timeout.
- `PlatformOS` singleton owns config/EventBus/MetricsCollector/HealthChecker and a
  validated `LifecycleState` machine (incl. PAUSED/RECOVERING via
  `PlatformOS.pause()/resume()`).
- `create_platform()` already calls `initialize()` — do NOT call `initialize()` again
  before `start()` (invalid transition).

## CRITICAL historical bug (fixed 2026-08-04) — why modules used to not boot

`discover()` only looked up `_MODULE_REGISTRY[name]` **without ever importing the
module package**. `_MODULE_REGISTRY` is populated only when a package is imported, so
every `record.module_class` stayed `None` and `initialize_all()` (which filters
`module_class is not None`) silently initialized NOTHING. Fix: `discover()` must call
`import_module(name)` (and the record must be added to `_records` BEFORE the import, or
`import_module` early-returns None). When adding/verifying module discovery, always
assert `record.module_class is not None` — a bare "record exists" check won't catch it.

## How to add a NEW module

```
modules/<name>/__init__.py        exports __version__, create_<name>_module(config), re-exports
modules/<name>/<name>.py          the real @module-decorated Module subclass + facade
modules/<name>/tests/test_*.py    hermetic tests
```

- `__init__.py` must define a `@module(name='<name>', version='<ver>')`-decorated
  `Module` subclass implementing `initialize`/`health_check`/`shutdown`, and expose
  `create_<name>_module(config)`. (Subagents place the class in the impl file and
  import it into `__init__.py` — either works; be consistent with nearby modules.)
- Preserve ALL existing public exports of a module you're touching — existing tests
  import facade names directly.
- Wire it into `config.yaml` under top-level `modules:<name>:` (enabled, priority,
  required, config).
- Keep it stdlib-only unless deps are already in requirements.txt.

## Two-kernel / duplication smell (know before you edit)

- `kernel/` is a SEPARATE disconnected hand-rolled kernel (ModuleSpec, QualityGate
  with string `check_fn` that is never evaluated, SQLite hash-chained AuditTrail).
  It is NOT wired to `platform_kernel.py`. Consolidating it into the real kernel is a
  large, flagged-but-not-done refactor.
- Duplicated subsystems (choose the *registered* one, don't add a third):
  `integration/event_hub.EventBus` (richer: schemas/replay/tracing) vs
  `platform_kernel.EventBus` (the one used);
  2+ MetricsCollectors (`monitoring/metrics_collector.MonitoringMetricsCollector` is
  the full one with Prometheus export);
  2 plugin frameworks, 2 workflow composers, 2 feature-flag engines, 2 tenant managers,
  ʻfoundation/*` vs `orchestration/`+`tenancy/`.
- 27/37 modules were kernel-registered; the 10 big "OS" modules
  (safety_governance, privacy_data, prompt_context, developer_experience,
  agent_coordination, knowledge_graph, customer_experience, release_change,
  disaster_recovery, innovation_rd) were NOT — all now registered (2026-08-04).

## Memory/knowledge stack overlaps (4 competing layers)
`memory` + `semantic_memory` + `kb_bridge` + `knowledge_graph` overlap. semantic_memory
was upgraded (2026-08-04) with a mem0-style hybrid core (`modules/semantic_memory/
hybrid.py`: HybridSemanticMemory, AddResult{created,updated,noop}, SQLite persistence).

## Verified rip-patterns already landed (all MIT/Apache-2.0, stdlib-reimplemented)
- `modules/model_router/` — LiteLLM retry/cooldown model router (CooldownCache,
  per-exception retry, weighted dispatch, max_fallbacks, HTTPAdapter + offline
  EchoAdapter for hermetic tests).
- `modules/llmops_trace/otel_genai.py` — OpenTelemetry GenAI semantic-convention
  tracing (contextvars span stack, gen_ai.* attrs, sampling, Console/Jsonl/Prometheus
  exporters).

## Testing
Run from repo cwd (`cd ~/Desktop/Enterprise Builder/enterprise`):
`python3 -m pytest -q -p no:cacheprovider` (3027 passed as of 2026-08-04).
`python3 -m pytest modules/<name> -q -p no:cacheprovider` for one module.
