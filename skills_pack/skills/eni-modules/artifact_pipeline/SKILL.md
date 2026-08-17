---
name: eni-module-artifact_pipeline
description: Operate the ENI Enterprise `artifact_pipeline` module (Legacy Core) — Artifact Pipeline — navigate & organize all creative works (no LLM). Use when working with artifact_pipeline in the Enterprise Platform.
---

# Module skill: artifact_pipeline

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Artifact Pipeline — navigate & organize all creative works (no LLM).

## What it does
Artifact Pipeline — navigate & organize all creative works (no LLM).

Grounded in the JEVanClief transcript *"Watch Me Build Something Claude Code
Can't Do Yet"* (https://www.youtube.com/watch?v=KC0VEZuo4OI, 891s). JEVanClief
explicitly does NOT want a front end that calls Claude (to dodge API fees); he
wants a front end that lets him navigate all of his works, take scripts and turn
them into "full animations", with a workflow that is "much more organized and
clear", and finished animations viewable in one place.

That is an asset / pipeline ORGANIZER — an `ArtifactRegistry` that catalogs
files on disk (Path-based scanning), tracks per-artifact TYPE and STAGE, a
`WorkflowGraph` of valid stage transitions (``script -> storyboard ->
animation -> render`` plus the transcript-grounded shortcut

## Key API (facade methods on the @module class)
- add\n- advance\n- all_renders\n- browse\n- derive\n- group_by\n- health\n- health_check\n- initialize\n- pipeline\n- readiness\n- set_event_bus\n- shutdown

## Use
Import via:
```python
from enterprise.modules.artifact_pipeline import create_artifact_pipeline_module
m = create_artifact_pipeline_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/artifact_pipeline/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
