# Module: `artifact_pipeline`

- Category: Legacy Core · priority 14
- Version: 1.0.0
- Purpose: Artifact Pipeline — navigate & organize all creative works (no LLM).
- Skill: `eni-module-artifact_pipeline` (ICM stages) in skills_pack/skills/eni-modules/artifact_pipeline/

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
animation -> render`` plus the transcript-grounded shortcut ``script ->
animation``), dependency tracking (a render depends on its script), and a local
catalog store (JSON / SQLite, in-memory + tmp_path) — all stdlib, network-free.

The deterministic core lives in
:mod:`enterprise.modules.artifact_pipeline.artifact_pipeline`; this package
exposes it as a registered Platform Kernel module with an initialize /
health_check / shutdown lifecycle and a thin facade.

## Key API (facade methods)
add, advance, all_renders, browse, derive, group_by, health, health_check, initialize, pipeline, readiness, set_event_bus, shutdown

## Tests
```bash
python3 -m pytest modules/artifact_pipeline/tests -q
```

## Import
```python
from enterprise.modules.artifact_pipeline import create_artifact_pipeline_module
m = create_artifact_pipeline_module()
```
