# Module: `model_psychometrics`

- Category: Domain · priority 4
- Version: 1.0.0
- Purpose: Probe/evaluate model reasoning attributes (psychometric-style evals).
- Skill: `eni-module-model_psychometrics` (ICM stages) in skills_pack/skills/eni-modules/model_psychometrics/

## What it does
Enterprise Model Psychometrics OS Module — audit the trait profile of AI
models with validated psychometric scales.

Grounded in JEVanClief's "ethics engine" / "becoming an AI psychologist"
pipeline (data/transcripts/JEVanClief/UGyTimVObus.md and Wtf6E-fwuwI.md): a
data pipeline that administers validated personality / psychometric scales
(right-wing authoritarianism, moral foundations, social dominance, Rosenberg
self-esteem) across AI models, personas, model variations and providers to tell
you where a model "lands" on moral foundations / authoritarianism / personality
dimensions.

Module design (mirroring the transcript's own engineering notes):
  * Scales are data — name, description, citation, Likert response range,
    item text, reverse-score flags — and users can select built-ins or add
    custom scales.
  * The pipeline runs scales against AI models through a provider-adapter
    interface. Real providers need credentials and degrade gracefully when
    none are present; the core is network-free and stdlib-only.
  * Stateless by design: no secrets are stored (matches the transcript's
    "it is stateless / doesn't save any personal information").

Version: 1.0.0
Python: 3.10+

## Key API (facade methods)
health_check, initialize, registry, runner, set_event_bus, shutdown

## Tests
```bash
python3 -m pytest modules/model_psychometrics/tests -q
```

## Import
```python
from enterprise.modules.model_psychometrics import create_model_psychometrics_module
m = create_model_psychometrics_module()
```
