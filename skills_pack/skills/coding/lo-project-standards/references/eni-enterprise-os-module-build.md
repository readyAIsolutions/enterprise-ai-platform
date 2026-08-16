# ENI Enterprise Platform — OS Module Build Contract

Proven contract for adding a capability module to the Enterprise AI Platform at
`~/Desktop/Enterprise Builder/enterprise` (GitHub: `readyAIsolutions/enterprise-ai-platform`).
Verified 2026-08-02: shipped 4 modules in one pass (`skill_factory`, `task_harness`,
`gateway`, `semantic_memory`) = 160 new tests; full suite 1982 → 2142, 0 failures.

## Module layout (mirror `modules/kb_bridge/` as the reference)

```
modules/<name>/__init__.py     # @module-decorated Module subclass + __version__ + __all__
modules/<name>/<name>.py       # core logic, keep __init__.py thin (like kb_bridge.py)
modules/<name>/tests/test_*.py # real unit tests
```

`__init__.py` essentials:
```python
from enterprise.platform_kernel import Module, module, HealthStatus, EventBus, EventPriority

@module(name="<name>", version="1.0.0")
class XxxModule(Module):
    def __init__(self, config=None):
        super().__init__(config)          # sets self._config, self._status=HealthStatus.UNKNOWN
        self._event_bus = None
    async def initialize(self) -> None: ...   # HEALTHY on success, UNHEALTHY on failure (re-raise)
    async def health_check(self) -> HealthStatus: ...
    async def shutdown(self) -> None: ...
    def set_event_bus(self, event_bus: EventBus): self._event_bus = event_bus
```
- `Module` base already provides `name` / `version` / `status` / `config` / `module_id`
  properties — do NOT redefine; only implement the three abstract methods + `set_event_bus`.
- `HealthStatus`: `UNKNOWN, STARTING, HEALTHY, UNHEALTHY, STOPPING`.
- Publish events via `self._event_bus.publish(...)` — always guard `if self._event_bus:`.

## Discovery — ZERO kernel edits
`ModuleRegistry.discover()` scans `modules/*/__init__.py`, reads `__version__`, and binds
the class from `_MODULE_REGISTRY` (populated by the `@module` decorator). Drop a compliant
module in and it auto-registers. To enable/order, add a block to `config.yaml` under
`modules.<name>` (`enabled`, `priority`, `required`, `startup_timeout_sec`,
`health_check_interval_sec`, `config: {...}`). Never edit `platform_kernel.py`.

## pytest conventions (pyproject.toml)
- `testpaths = ["tests", "modules"]`, `pythonpath = ["."]`, `--strict-markers`,
  `asyncio_mode = "auto"` (plain `async def test_...`).
- Import modules as `enterprise.modules.<name>` in tests (NOT `modules.<name>`) to keep a
  single class identity in `_MODULE_REGISTRY` (a duplicate identity breaks `issubclass`).
- Use `tmp_path` for file/DB IO — tests must never touch the repo (no fake data / no
  pollution). Confirm `git status` shows no `data/` or new roots created.

## Design rules (LO standards)
- **Dependency-free cores**: stdlib only (sqlite3, dataclasses, hashlib, urllib). Optional
  external libs wrapped in try/except; never crash at import.
- **Inject adapters for external services**: opener callable for HTTP, fake embedder for
  vectors, FakeChannel for messaging — tests need zero network.
- Lifecycle idempotent; emit meaningful events.

## Parallel-delegation build pattern
To ship several modules in one pass: loan each independent module to a parallel
`delegate_task` leaf subagent, giving each the exact contract above + "mirror kb_bridge",
"test only YOUR module dir (`python3 -m pytest modules/<name>/tests -q`)", "do NOT run the
full suite", "do NOT edit config.yaml/platform_kernel.py". Then integrate yourself: add
config.yaml entries → run FULL suite → fix → docs/STATUS → commit → push. All 4 landed clean
in one pass this way.

## Pushing to GitHub
- Remote SSH: `git@github.com-enterprise:readyAIsolutions/enterprise-ai-platform.git`;
  key `~/.ssh/enterprise_ai_platform` (fingerprint `SHA256:qhItmXU784XlfoUL+VZlnnljlO8bF3QBwdREw3V5njM`,
  GitHub user Mimicry500). Confirm with `ssh -T -i ~/.ssh/enterprise_ai_platform git@github.com`.
- `main` is **branch-protected** ("changes must be made through a pull request") — direct
  `git push origin main` is rejected (remote GH013). Push a feature branch:
  `git branch -M <topic> && git push origin <topic>` → remote prints the
  `pull/new/<branch>` URL → open PR from it. `gh pr create` / GH_TOKEN are not configured
  on this box, so the web link is the way to merge.
- Hygiene: the repo had stray TRACKED `__pycache__/*.pyc` (committed before .gitignore).
  Untrack them with `git rm -r --cached $(git ls-files '*.pyc')` and add `data/` to
  .gitignore so future test runs don't dirty the tree.

## Status/docs conventions
- Write `STATUS_ENTERPRISE_UPGRADE.md` with a PASS/FAIL board, "what adds R / what to drop",
  and an UNVALIDATED section (be truthful about what needs real infra/creds). Keep the
  README module table current. Convention: `STATUS_<TOPIC>.md` at the repo root / docs.
