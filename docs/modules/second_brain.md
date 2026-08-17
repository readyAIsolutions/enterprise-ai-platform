# Module: `second_brain`

- Category: Knowledge Intake · priority 1
- Version: 1.0.0
- Purpose: Knowledge capture/resurfacing engine: nodes+links, spaced repetition, concept query, compounding.
- Skill: `eni-module-second_brain` (ICM stages) in skills_pack/skills/eni-modules/second_brain/

## What it does
Second Brain module — a knowledge capture & resurfacing engine.

Grounded in three real pulled JE Van Clief transcripts:

  * "Your Second Brain Is Not a Notes App" (-CUsfao6m7E)  — a second brain
    links ideas and carries metadata; plain storage becomes a "graveyard".
  * "Van Squared: A Free Local AI Model Labeled a 26-Year Archive"
    (mme027WZhgo) — a labeled long-term archive stays searchable/compounds.
  * "AI Since 2011: The Ideas That Outlive Every Model" (lDXCkx3Nla8) — ideas
    and first principles outlive any single model or tool.

Export surface:
  * SecondBrain — the capture/link/resurface/query/compounding engine.
  * Entry       — a single captured node with metadata + review state.
  * SecondBrainModule — the ENI platform Module wrapper.
  * create_second_brain_module(config) — factory used by the platform.

## Key API (facade methods)
build_compounding_report, capture, health_check, initialize, link_ideas, query_concept, resurface, shutdown

## Tests
```bash
python3 -m pytest modules/second_brain/tests -q
```

## Import
```python
from enterprise.modules.second_brain import create_second_brain_module
m = create_second_brain_module()
```
