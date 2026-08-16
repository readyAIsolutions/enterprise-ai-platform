# STATUS — AI Coding Harness (ai_coding_harness)

**Builder:** subagent (demiurge enterprise boost) · **Date:** 2026-08-16
**Branch:** `upgrade/demiurge-enterprise-boost`
**Module path:** `modules/ai_coding_harness/`

## Summary

New enterprise module implementing the *repeatable agentic Claude-Code coding
workflow* distilled from four pulled JE Van Clief transcripts: set up context
(CLAUDE.md / project.md), scaffold a project in folders, generate an editable
artifact from a prompt (site / HTML / SVG / React / animation), then iterate
and verify until it passes — plus the Remotion `script -> specification ->
scenes -> render` pipeline.

Pure, network-free engine (`harness.py`), wired into the ENI platform kernel
as a registered module.

## PASS/FAIL Board

| Check | Result |
|-------|--------|
| Module directory created (`modules/ai_coding_harness/`) | **PASS** |
| Core engine `harness.py` (pure, no numpy/pandas/requests) | **PASS** |
| `__init__.py` imports kernel, `@module` registered class | **PASS** |
| Facade `create_ai_coding_harness()` + factory `create_ai_coding_harness_module()` | **PASS** |
| pytest run: `python3 -m pytest modules/ai_coding_harness/tests -q` | **PASS — 15/15 passed** (0 failed) |
| Kernel registration check (`'ai_coding_harness' in _MODULE_REGISTRY`) | **PASS — True** |
| Committed on `upgrade/demiurge-enterprise-boost` | **PASS** |
| Commit SHA (feature commit, `git rev-parse HEAD` of the module commit) | `6d95948de4b0dc1af788cb492df40a76bcc19c10` |

## Grounding (transcripts consulted)

- `ozkx_eUfjY0` — No Wix/Squarespace, Claude Code + GitHub Pages: build context
  first, then prompt to scaffold + generate the site, host for free.
- `rHDA0WMXzy4` — Install Claude Code, work from the terminal, scaffold in
  folders instead of hand-copying.
- `izMBiWG3L24` — SVG-to-React with Remotion + UI/UX Pro skill: labeled SVGs,
  CLAUDE.md context ("where to go"), long natural-language iterate-and-verify
  loop over editable components.
- `vyN7ITKcGXU` — Remotion pipeline: script lab + animation studio folders,
  `script -> spec(storyboard) -> scenes -> render` stages, each editable.

Public API (see `__init__.py` `__all__`): `AiCodingHarness`,
`AiCodingHarnessModule`, `ContextSpec`, `ScaffoldSpec`, `Artifact`,
`GenerationPlan`, `VerificationResult`, `ArtifactKind`, `PipelineStage`,
`default_context`, `create_ai_coding_harness`, `create_ai_coding_harness_module`,
`__version__`.

## UNVALIDATED (honest notes)

- **Line-count/import check for `harness.py`**: manually trimmed to stay under
  ~700 lines but not programmatically asserted in CI.
- **Cross-module kernel-health e2e**: only the module's own `initialize` /
  `health_check` path is exercised by tests; the module was **not** run through
  the full `PlatformOS.start()` orchestrator / auto-discovery bootstrap.
- **Real model generation**: no actual Claude Code / model call is performed —
  `generate()` is a deterministic offline stand-in so the workflow shape is
  testable without a network. It has NOT been validated against a live model.
- **No integration with the integrator's `build/manifest.json` / `config.yaml`**
  (deliberately out of scope here).
- **Parallel builders**: this module did not touch other `modules/`,
  `platform_kernel.py`, the manifest, or config; no cron jobs scheduled.

## Issues Hit & Resolved

- **ENI compression on large `read_file`** of transcripts — worked around by
  reading in small slices and de-duplicating the triplicated transcript lines
  (each spoken line appeared 3×).
- **Pyright import warnings** (missing `enterprise.*`) — expected; they are
  static-language-server artifacts because `PYTHONPATH` isn't set for the LSP.
  pytest resolves imports via `pythonpath=["."]` in `pyproject.toml` (15 pass).
- **RENDER stage initially failed verification** (body lacked an exported
  component marker) — fixed by composing the render stage with the real
  deterministic `generate()` component body; then all 15 tests passed.
