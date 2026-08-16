# STATUS — DEMIURGE UPGRADE WAVE: artifact_pipeline

**Module:** `modules/artifact_pipeline/`
**Source transcript:** `data/transcripts/JEVanClief/KC0VEZuo4OI.md`
  — "Watch Me Build Something Claude Code Can't Do Yet" (JEVanClief, 891s)
**Branch:** `upgrade/demiurge-enterprise-boost`
**Engineer date:** 2026-08-17

## Thesis grounded in the transcript
The whole premise is stated in the first minute of the video: JEVanClief wants a
**front end that lets him navigate all of his works** in one organized, clear
place — and he explicitly does NOT want a front end that calls Claude, because
that would incur **API fees**. He wants to take scripts and turn them into
"full animations", with a workflow that is "much more organized and clear", and
finished animations viewable in one place.

> "I want to make a front end that lets me navigate all of my works here ...
> because I can take scripts and I can take them and turn them into ... full
> animations ... have my workflow to create these animations, but have it where
> it's much more organized and clear."

→ This is an asset / pipeline **ORGANIZER**, NOT a chatbot. The module therefore
implements a network-free `ArtifactRegistry` (Path-based on-disk catalog tracking
per-artifact TYPE and STAGE), a `WorkflowGraph` of valid stage transitions
(`script → storyboard → animation → render` with the transcript-grounded
shortcut `script → animation`), dependency tracking (a render depends on its
script), grouping/navigation by type/project/stage, and a local catalog store
(JSON + SQLite, in-memory + tmp_path persistence) — **no LLM is ever called**, so
no API fees, exactly as the transcript demands.

## What was built (public API)
* `ArtifactType` enum — `SCRIPT | STORYBOARD | ANIMATION | RENDER`.
* `Stage` enum + `STAGE_ORDER` — the four pipeline stages in order.
* `Artifact` dataclass — `id, path, name, project, type, stage, dependencies,
  metadata`; `is_viewable` flag (finished animations/renders).
* `WorkflowGraph` — `can_transition`, `next_stages`, `has_next`, `rank`,
  `strictly_before`, `edges`, `validate_transition`.
* `ArtifactRegistry` — `register`, `remove`, `get`, `filter(project, type, stage,
  viewable_only)`, `group_by(field)`, `scan(root)`, `stats()`; extension-based
  type inference (`infer_type`), stable sha1 ids (`id_for_path`).
* `ArtifactPipeline` — the organizer/navigator: `add`, `derive(source,
  output_path)` (turn a script into a full animation), `advance`, `can_advance`,
  `readiness`, `add_dependency`, `dependencies_of`, `dependents_of`, `browse`,
  `all_renders` (finished outputs "in one place"), `group_by`, `workflow`,
  `stats`, `persist`, `load_from_store`, `scan`.
* `JsonCatalogStore` / `SqliteCatalogStore` — local persistence (stdlib only).
* `ArtifactNotFoundError`, `DuplicateArtifactError`, `InvalidTransitionError`,
  `DependencyError`.
* `ArtifactPipelineModule` — ENI `@module(name="artifact_pipeline",
  version="1.0.0", config_defaults={scan_root, catalog_store, catalog_path})`
  wrapper with `initialize` (HEALTHY) / `health_check` / `shutdown`,
  `set_event_bus`, guarded event publishing (`Event.create` via
  `self._event_bus`, only when bus wired), and a thin facade (`add` / `derive` /
  `advance` / `browse` / `all_renders` / `group_by` / `readiness` / `health`).
* `create_artifact_pipeline_module(config)` factory + `__all__`.

## PASS / FAIL verification board (real numbers)
| # | Check | Result | Detail |
|---|-------|--------|--------|
| 1 | Module unit tests | **PASS** | **18 passed, 0 failed** (`python3 -m pytest modules/artifact_pipeline/tests -q` → `18 passed in 0.04s`) |
| 2 | Pipeline graph (script→animation shortcut) | **PASS** | `SCRIPT→{STORYBOARD,ANIMATION}`, `STORYBOARD→{ANIMATION}`, `ANIMATION→{RENDER}`, `RENDER→{}` terminal; backward/render-jump rejected |
| 3 | Type inference by extension | **PASS** | `.md/.txt`→SCRIPT, `.json`→STORYBOARD, `.anim`→ANIMATION, `.mp4`→RENDER, unknown→SCRIPT |
| 4 | On-disk scan + grouping | **PASS** | `scan(root)` catalogs all files; `group_by("project")` correct; `all_renders()` surfaces the 2 finished outputs under one name |
| 5 | derive: script → full animation → render | **PASS** | derived artifact gets downstream stage + auto dependency on source; dependency chain render→animation→script verified |
| 6 | Transition validation | **PASS** | invalid derive (render from fresh script) raises `InvalidTransitionError`; backwards advance rejected |
| 7 | Dependency validation | **PASS** | upstream must be strictly earlier; script→render valid, render→script rejected; self-dependency rejected |
| 8 | Readiness | **PASS** | `can_advance` → [storyboard, animation]; after advance `next == ["render"]` |
| 9 | JSON store roundtrip | **PASS** | persist→load restores all 2 artifacts with correct names |
| 10 | SQLite store roundtrip | **PASS** | persist→load restores artifact; `close()` works (stdlib sqlite3) |
| 11 | Module lifecycle | **PASS** | initialize→HEALTHY; health_check→HEALTHY; shutdown→UNKNOWN |
| 12 | Module unhealthy when uninitialized | **PASS** | health_check on fresh module → UNHEALTHY |
| 13 | Event bus wiring | **PASS** | with bus set (sync dispatch), `artifact_pipeline.added` event received; without bus, no crash |
| 14 | Platform registration | **PASS** | `PYTHONPATH=… python3 -c "from enterprise.platform_kernel import _MODULE_REGISTRY; import enterprise.modules.artifact_pipeline; print('artifact_pipeline' in _MODULE_REGISTRY)"` → **True** |
| 15 | Network-free core | **PASS** | pure stdlib (`json`, `sqlite3`, `re`, `hashlib`, `pathlib`, `dataclasses`, `enum`); no sockets/http; tmp_path only in tests |
| 16 | Core size | **PASS** | `artifact_pipeline.py` = 648 lines (stdlib-only pure core); `__init__.py` = 238 lines (kernel facade) |

## UNVALIDATED (not verified by this subagent)
| Item | Reason |
|------|--------|
| Full-suite regression across all modules (`pytest` at repo root) | Out of scope — task forbids touching/altering other modules; only this module's tests were run (18/18). |
| Whole-platform boot / dashboard integration | Requires running the full ENI Platform (out of scope for this module task). |
| Ruff / mypy lint gates | Not part of this task's acceptance checklist; not run. |
| Live end-to-end against a real creative-works directory | Validated with synthetic `tmp_path` fixtures only; no real user content was used. |
| Any LLM/API-fee path | **N/A by design** — this module deliberately contains no LLM call (the transcript's whole point). |

## Files touched (only module + this doc)
* `modules/artifact_pipeline/__init__.py`
* `modules/artifact_pipeline/artifact_pipeline.py`
* `modules/artifact_pipeline/tests/test_artifact_pipeline.py`
* `docs/STATUS_DEMIURGE_ARTIFACT_PIPELINE.md`

No changes to `config.yaml`, `platform_kernel.py`, other modules, the full
suite, or `data/build/manifest.json` (ledger handled centrally by the parent).
