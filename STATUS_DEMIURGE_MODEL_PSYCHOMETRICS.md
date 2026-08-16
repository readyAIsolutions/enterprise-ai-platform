# STATUS — Model Psychometrics Module v1.0.0 (DEMIURGE WAVE)
Date: 2026-08-17  |  Module: `modules/model_psychometrics`  |  Target: audit the trait
profile of AI models with validated psychometric scales.

## Source
Grounded in **two JEVanClief transcripts** under `data/transcripts/JEVanClief/`:
- `UGyTimVObus.md` — *"From Nazi Psychology to AI Auditing: Inside the System I Built"* (13.7 min)
  — the "ethics engine": a data pipeline that takes validated personality tests
  and aims them across AI models, personas, model variations and providers to say
  where a model lands on moral foundations / authoritarianism / personality
  dimensions. Models are function calls; the orchestration (async, rate limits,
  retries, queueing) + data processing (~60% of code) is traditional engineering.
- `Wtf6E-fwuwI.md` — *"Becoming an AI Psychologist: A data Pipeline for Researchers"* (8.5 min)
  — tutorial walkthrough: select scales (RWA, moral foundations, social dominance,
  Rosenberg self-esteem), add custom scales (name, description, citation, response
  points 1-7 / 1-5, item text, reverse-scored), supply per-provider API keys
  (OpenAI, Anthropic, xAI, self-hosted), pick personas, set temperature & runs,
  then async per-item-per-model calls compiled to JSON + CSV. **Stateless**:
  "they're not stored … it doesn't save any personal information about you."

## What was built
- **Pure core** (`model_psychometrics.py`, stdlib-only, network-free):
  - `PsychometricItem(text, reverse_scored)` and `PsychometricScale(name,
    description, citation, response_max, items)` with reverse-scoring
    `(response_max+1) - raw`, midpoint, add_item.
  - Four built-in validated scales (RWA, moral-foundations, social-dominance,
    rosenberg-self-esteem) with citations + a small set of *illustrative* items
    (clearly marked, not the full published instrument).
  - `ScaleRegistry` (pick built-ins, add custom scales).
  - `ProviderAdapter` (abstract) + `TestProvider` (deterministic), `NoopProvider`
    (never ready → graceful `ok:False`), `RealProvider` (needs_credentials /
    has_credentials flag; degrades gracefully with **no HTTP**).
  - `ModelPsychometricsRunner` → `ScaleResult` (sum/mean/stdev, per-item
    normalized 0..1, textual heuristic interpretation) → `ProfileReport` →
    `BatchReport` across multiple model/persona/provider profiles.
  - Helper `build_custom_scale()` + `summarize_battery()`.
- **Module wrapper** (`__init__.py`): `@module(name="model_psychometrics",
  version="1.0.0", config_defaults=...)` class with async initialize / health_check
  / shutdown, `set_event_bus`, optional `Event` publish only when a bus is wired,
  and `create_model_psychometrics_module(config)`.
- **Tests** (`tests/test_model_psychometrics.py`): 41 tests, pytest asyncio_mode=auto.

## PASS / FAIL board (real evidence)
| Check | Result | Evidence |
|-------|--------|----------|
| Reverse-scoring math  | **PASS** | 1-7 & 1-5 reversal, clamped to window; 4 tests |
| Aggregation math      | **PASS** | sum/mean/stdev/normalized 0..1; 5 tests |
| Built-in preset scales| **PASS** | RWA, moral-foundations, social-dominance, rosenberg present |
| Custom scale add      | **PASS** | build + registry add/get/require |
| Multi-profile run report | **PASS** | 3-model battery → 3 ok reports |
| Noop / no-cred degrade| **PASS** | `ok:False` structured, no network, no crash |
| Provider abstraction  | **PASS** | abstract base not instantiable |
| Module lifecycle      | **PASS** | initialize→HEALTHY, health_check→HEALTHY, shutdown |
| Module factory        | **PASS** | `create_model_psychometrics_module` works |
| Event publish (wired) | **PASS** | EventBus subscribe received `model_psychometrics.initialized` |
| Unit tests            | **PASS** | `pytest modules/model_psychometrics -q` → **41 passed, 0 failed** |
| Platform registration | **PASS** | `'model_psychometrics' in _MODULE_REGISTRY` → **True** |
| Git branch / commit   | **PASS** | committed on `upgrade/demiurge-enterprise-boost` (see SHA) |

## What adds R / what to drop
- **Adds R:** a first-class, stateless, network-free psychometric audit pipeline
  grounded directly in the JEVanClief research pipeline — tells you where a model
  "lands" on moral foundations / authoritarianism / self-esteem / SDO, reusable
  across providers and personas. JSON-friendly `to_dict()` for downstream research
  tooling.
- **Keep:** provider-adapter degradation (no credentials → graceful ok:False),
  stdlib-only core, illustrative-but-cited scale presets, custom-scale support.
- **Drop / not implemented (by design):** real HTTP scoring (out of scope and
  prohibited here), automatic model discovery via API keys, persona auto-generation
  (AI-driven), reliability statistics (Cronbach alpha / test-retest), CSV/JSON
  compilation to a shared database, security/auth. These are recorded as the
  transcript's roadmap and left UNVALIDATED rather than faked.

## UNVALIDATED
- Real-provider HTTP scoring against OpenAI/Anthropic/xAI (would require live API
  keys + network; explicitly not exercised — this module is network-free by design).
- Full published-length scales (RWA 30-item, SDO 16-item, RSES 10-item, full MFQ):
  only a few representative items per scale are shipped and are clearly marked
  illustrative; a complete administration needs the full instruments.
- Cronbach's alpha / test-retest reliability figures: the transcript cites these
  (via scipy/numpy) but they are not implemented and were not measured here.
- Cross-validation of the textual interpretation heuristic against human profiles.
