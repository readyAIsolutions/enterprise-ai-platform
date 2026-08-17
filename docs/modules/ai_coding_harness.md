# Module: `ai_coding_harness`

- Category: Agent Workflow · priority 2
- Version: 1.0.0
- Purpose: Harness for coding-agent output: run, verify, audit.
- Skill: `eni-module-ai_coding_harness` (ICM stages) in skills_pack/skills/eni-modules/ai_coding_harness/

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
  * create_ai_coding_harness()  — build a bare engine.
  * create_ai_coding_harness_module(config) — build the kernel module.

## Key API (facade methods)
build_context, generate_from_prompt, health_check, initialize, scaffold, shutdown

## Tests
```bash
python3 -m pytest modules/ai_coding_harness/tests -q
```

## Import
```python
from enterprise.modules.ai_coding_harness import create_ai_coding_harness_module
m = create_ai_coding_harness_module()
```
