---
name: eni-module-information_theory
description: Operate the ENI Enterprise `information_theory` module (Legacy Core) — information_theory — Shannon entropy, mutual information, KL divergence, and Use when working with information_theory in the Enterprise Platform.
---

# Module skill: information_theory

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: information_theory — Shannon entropy, mutual information, KL divergence, and

## What it does
information_theory — Shannon entropy, mutual information, KL divergence, and
a Wordle-style expected-information-gain solver, as an enterprise module.

Grounded in real source transcripts:

* StatQuest *"Entropy (for data science) Clearly Explained!!!"*
  (https://www.youtube.com/watch?v=YtebGVx-Fxw): surprise = log2(1/p); entropy
  is the expected surprise.
* StatQuest *"Mutual Information Clearly Explained!!!"*
  (https://www.youtube.com/watch?v=eJIp_mgVLwE): MI(X;Y) = H(X) - H(X|Y).
* 3blue1brown *"Solving Wordle using information theory"*
  (https://www.youtube.com/watch?v=v68zYyaEmEA) and follow-up
  (https://www.youtube.com/watch?v=fRed0Xmc2Wg): expected information gain of a
  guess = entropy over its feedback-pattern distribution; pick the max.

The deterministic core lives in
:mod

## Key API (facade methods on the @module class)
- best_guess\n- conditional_entropy\n- entropy\n- entropy_from_counts\n- expected_information_gain\n- health_check\n- initialize\n- joint_entropy\n- kl_divergence\n- mutual_information\n- set_event_bus\n- shutdown\n- surprise\n- wordle_feedback

## Use
Import via:
```python
from enterprise.modules.information_theory import create_information_theory_module
m = create_information_theory_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/information_theory/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
