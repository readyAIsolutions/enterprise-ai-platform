# Module: `information_theory`

- Category: Legacy Core · priority 40
- Version: 1.0.0
- Purpose: information_theory — Shannon entropy, mutual information, KL divergence, and
- Skill: `eni-module-information_theory` (ICM stages) in skills_pack/skills/eni-modules/information_theory/

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
:mod:`enterprise.modules.information_theory.core`; this package registers it as
a kernel module with an initialize / health_check / shutdown lifecycle and a
thin facade.

## Key API (facade methods)
best_guess, conditional_entropy, entropy, entropy_from_counts, expected_information_gain, health_check, initialize, joint_entropy, kl_divergence, mutual_information, set_event_bus, shutdown, surprise, wordle_feedback

## Tests
```bash
python3 -m pytest modules/information_theory/tests -q
```

## Import
```python
from enterprise.modules.information_theory import create_information_theory_module
m = create_information_theory_module()
```
