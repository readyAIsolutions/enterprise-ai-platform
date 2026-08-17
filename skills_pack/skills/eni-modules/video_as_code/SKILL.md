---
name: eni-module-video_as_code
description: Operate the ENI Enterprise `video_as_code` module (Domain) — Represent/edit long-form video (animations) as code/scripts. Use when working with video_as_code in the Enterprise Platform.
---

# Module skill: video_as_code

- Category: Domain (priority 4)
- Version: 1.0.0
- Purpose: Represent/edit long-form video (animations) as code/scripts.

## What it does
Video as Code Enterprise Module.

Grounded in the JEVanClief talk *"Video as Code: My AI Animation Stack"*
(https://www.youtube.com/watch?v=yEa6dgh7wuc). Treats AI video/animation
generation as software engineering applied to a creative problem, where the
hard work is the spec (a markdown "brief") rather than the AI or the code.
A loose spec makes the agent "make more interpretive choices or hallucinate
more"; a tight spec "directs it at every beat" — *"Give me the freedom of a
tight brief."*

This module expose a network-free, stdlib-only spec-driven generation pipeline:

  * ``VideoSpec`` / ``Scene`` — structured brief model.
  * ``parse_spec_markdown`` / ``spec_from_dict`` — describe a brief.
  * ``validate_spec`` — warns on missing/loose fields.
  * ``tightness_score`` / ``hallucinatio

## Key API (facade methods on the @module class)
- event_bus\n- health_check\n- initialize\n- run_pipeline\n- runner\n- set_event_bus\n- shutdown

## Use
Import via:
```python
from enterprise.modules.video_as_code import create_video_as_code_module
m = create_video_as_code_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/video_as_code/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
