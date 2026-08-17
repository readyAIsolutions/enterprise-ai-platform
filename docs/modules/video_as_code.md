# Module: `video_as_code`

- Category: Domain · priority 4
- Version: 1.0.0
- Purpose: Represent/edit long-form video (animations) as code/scripts.
- Skill: `eni-module-video_as_code` (ICM stages) in skills_pack/skills/eni-modules/video_as_code/

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
  * ``tightness_score`` / ``hallucination_risk_estimate`` — tightness scoring.
  * ``PipelineRunner`` — spec -> (optional generation) -> assembly manifest ->
    final artifact. Generation is an injectable deterministic ``StubGenerator``;
    the ``RealGenerator`` interface degrades gracefully (ok: False) when no
    external tooling is available.

Exports:
  VideoAsCodeModule — @module-decorated Module subclass
  plus the pure pipeline API from .video_as_code.

Version: 1.0.0
Python: 3.10+

## Key API (facade methods)
event_bus, health_check, initialize, run_pipeline, runner, set_event_bus, shutdown

## Tests
```bash
python3 -m pytest modules/video_as_code/tests -q
```

## Import
```python
from enterprise.modules.video_as_code import create_video_as_code_module
m = create_video_as_code_module()
```
