---
name: eni-module-ai_coding_harness
description: Operate the ENI Enterprise `ai_coding_harness` module (Agent Workflow) — Harness for coding-agent output: run, verify, audit. Use when working with ai_coding_harness in the Enterprise Platform.
---

# Module skill: ai_coding_harness

- Category: Agent Workflow (priority 2)
- Version: 1.0.0
- Purpose: Harness for coding-agent output: run, verify, audit.

## What it does
AI Coding Harness module — repeatable agentic Claude-Code coding workflows.

Implements the prompt->scaffold->generate->iterate->verify loop that
JE Van Clief demonstrates across four transcripts (websites from a prompt,
installing Claude Code, SVG-to-React animations, and the Remotion
script->spec->scenes->render pipeline).

The pure, offline engine lives in :mod:`harness`; this file wires it into the
ENI platform kernel as a registered module.

Public export surface:
  * AiCodingHarness        — the core engine (context, scaffold, plan, generate,
                             verify, iterate, run_stages).
  * ContextSpec, ScaffoldSpec, Artifact, GenerationPlan, VerificationResult,
    ArtifactKind, PipelineStage — value types surfaced by the engine.
  * create_ai_coding_harness()  — build

## Key API (facade methods on the @module class)
- build_context\n- generate_from_prompt\n- health_check\n- initialize\n- scaffold\n- shutdown

## Use
Import via:
```python
from enterprise.modules.ai_coding_harness import create_ai_coding_harness_module
m = create_ai_coding_harness_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/ai_coding_harness/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
