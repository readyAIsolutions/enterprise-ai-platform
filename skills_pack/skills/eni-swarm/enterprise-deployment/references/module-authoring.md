# Enterprise Platform — Authoring a New Kernel Module

Verified 2026-08-02 while adding the autonomy & tooling layer (skill_factory, task_harness,
gateway, semantic_memory) via 4 parallel swarm subagents. Result: 160 new tests, full suite
1982 → 2142 passed, kernel booted to `running` with 23 modules discovered.

## Kernel module contract (from `platform_kernel.py`)

- A module is a directory `modules/<name>/` with `__init__.py` (thin) + sibling logic file(s),
  mirroring `modules/kb_bridge/` (the clean reference example).
- `__init__.py` sets `__version__` and `__all__`, and defines:
  ```python
  @module(name="<name>", version="1.0.0")
  class <Name>Module(Module):
      def __init__(self, config=None):
          super().__init__(config)          # sets self._config, self._status=UNKNOWN, self._module_id
          self._event_bus = None
      async def initialize(self) -> None: ...
      async def health_check(self) -> HealthStatus: ...
      async def shutdown(self) -> None: ...
      def set_event_bus(self, eb): self._event_bus = eb
  ```
- Base `Module` already provides `name` / `version` / `status` (settable) / `config` / `module_id`
  properties and `_meta_name`/`_meta_version`/`_meta_config` set by the `@module` decorator.
- `HealthStatus` values: `UNKNOWN, STARTING, HEALTHY, UNHEALTHY, STOPPING` (also DEGRADED exists).
- In `initialize` set `self._status = HealthStatus.HEALTHY` on success, `UNHEALTHY` on failure and re-raise.
- Registry import path is `enterprise.modules.<name>`; tests must import via that (not `modules.<name>`),
  or the registry holds a duplicate class identity and `issubclass` checks fail.

## Discovery & registration

- `ModuleRegistry.discover()` scans `modules/*/__init__.py`, reads `__version__`, and matches
  `@module`-decorated classes in `_MODULE_REGISTRY` by directory name. Auto-enables by default
  (`enabled=True`); you register in `config.yaml` only to set priority/timeouts/config.
- No kernel edits needed. Add `modules/<name>/` and a `config.yaml` entry:
  ```yaml
  modules:
    my_module:
      enabled: true
      priority: 11
      required: false
      startup_timeout_sec: 15
      health_check_interval_sec: 60
      config:
        some_key: value
  ```
- Loader reads `modules.<name>.path`/`modules.<name>.<rest>` from config; unknown modules get defaults.

## Test conventions (pyproject.toml)

- `testpaths = ["tests", "modules"]`, `pythonpath = ["."]`, `asyncio_mode = "auto"` (plain `async def test_`),
  `--strict-markers` (markers must be declared), `-p no:anyio`, `-p no:cacheprovider`.
- Run just your module: `python3 -m pytest modules/<name>/tests -q`. Target 30-60 real tests per module.
- All file/DB/IO in tests uses `tmp_path` fixture. No fake data, no network (inject adapters).

## Parallel swarm build recipe

Each of the 4 modules was delegated to a separate leaf subagent (isolated context/terminal) with:
- WORK-ONLY path restriction (`modules/<name>/` only; don't touch config.yaml/kernel/other modules).
- The exact kernel interface above copied verbatim into the context.
- "Run `pytest modules/<name>/tests -q` and FIX until green" (never the full suite in the child).
- Per-module design spec + stdlib-only requirement + injectable adapters.
Charts: skill_factory 44, task_harness 29, gateway 56, semantic_memory 31 tests, all passing.

## Boot/integration verification gotcha

`PlatformOS.initialize()` is SYNC; `await p.start()` is async:
```python
p = PlatformOS.instance()
p.initialize(config_path=Path(repo)/"config.yaml", modules_path=Path(repo)/"modules")
await p.start()
```
- Pass `Path` objects, not `str` (ConfigurationLoader does `path.exists()`).
- Follow `lo-project-standards` PITFALL 6: any optional third-party import inside a module must be
  wrapped in try/except so `import enterprise.platform_kernel` / module discovery never crashes.

## Push to the GitHub repo

Repo: `readyAIsolutions/enterprise-ai-platform` (SSH `git@github.com-enterprise`), branch `main` is
**protected** → direct push rejected (GH013). Workflow that worked:
```bash
git add -A && git commit -m "..."
git branch -M upgrade/<feature>
git push origin upgrade/<feature>   # remote prints the PR "pull/new/..." URL
```
`gh pr create` needs auth (GH_TOKEN / `gh auth login`); if unauthenticated, hand LO the PR link to click.
