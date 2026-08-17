# Module: `eval_gate`

- Category: Legacy Core · priority 27
- Version: 1.0.0
- Purpose: ENI Eval Gate OS Module — automated LLM evaluation gates (local & offline).
- Skill: `eni-module-eval_gate` (ICM stages) in skills_pack/skills/eni-modules/eval_gate/

## What it does
ENI Eval Gate OS Module — automated LLM evaluation gates (local & offline).

Local, stdlib-only automated evaluation of model output quality using fully
deterministic lexical/heuristic metrics (no external model or service calls).
Mirrors the ``model_security`` philosophy: every metric is a regex- and
term-overlap-based function that can be unit tested offline.

Metrics implemented (computed from text alone):
  - AnswerRelevancy    — relevance proxy via answer/question token overlap.
  - Faithfulness       — groundedness of the answer relative to a source.
  - ToxicityDetector   — banned-word lexicon scan for profane content.
  - HallucinationProxy — fact-consistency proxy (unsupported-claim fraction).
  - RefusalDetector    — refusal / evasion phrasing detection.
  - JailbreakGuard     — jailbreak / prompt-injection attempt detection.

An :class:`EvalGate` enforces thresholds + policy (fail if any required metric
is below its minimum), :class:`EvalRunner` aggregates over sample dicts, and
:class:`EvalGateFacade` exposes the public surface behind the @module-decorated
:class:`EvalGateModule`.

All components are stdlib-only, zero external dependencies.

## Key API (facade methods)
(module-level API)

## Tests
```bash
python3 -m pytest modules/eval_gate/tests -q
```

## Import
```python
from enterprise.modules.eval_gate import create_eval_gate_module
m = create_eval_gate_module()
```
