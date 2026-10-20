# STATUS — DEMIURGE: information_theory module

Branch: `upgrade/demiurge-enterprise-boost`
Module: `modules/information_theory/` (NEW)

## PASS/FAIL board (real numbers)

| Check | Result | Evidence |
|-------|--------|----------|
| pytest `modules/information_theory/tests` | **PASS** | `36 passed in 0.04s` |
| Module registration in `_MODULE_REGISTRY` | **PASS** | prints `True` |
| Fair-coin entropy = 1.0 bit | PASS | `shannon_entropy([0.5,0.5]) == 1.0` |
| Certain outcome entropy = 0.0 | PASS | `shannon_entropy([1.0,0.0]) == 0.0` |
| Uniform 4-way entropy = 2.0 bits | PASS | test_uniform_four_outcomes_two_bits |
| MI of independent vars ~ 0 | PASS | `mutual_information(indep) ≈ 0` |
| MI(copy) = H(X) = 1 bit | PASS | test_mi_dependent_equals_marginal_entropy |
| MI = H(X) - H(X\|Y) identity | PASS | test_mi_equals_hx_minus_h_x_given_y |
| KL(p‖p) = 0 | PASS | test_kl_self_is_zero |
| KL undefined when q=0 under p>0 | PASS | raises ValueError |
| wordle_feedback('crane','crane') all-green | PASS | `(GREEN,)*5` |
| best_guess picks higher-entropy guess | PASS | `best_guess(...) == 'abcde'` |

## Module API

Core (`core.py`, stdlib `math` only):
- `surprise(p)` = -log2(p)
- `shannon_entropy(probabilities)` = Σ p·log2(1/p)
- `entropy_from_counts(counts)`
- `joint_entropy(joint)`, `conditional_entropy(joint)` = H(X,Y)-H(Y)
- `mutual_information(joint)` = H(X)-H(X|Y)
- `kl_divergence(p, q)`
- `wordle_feedback(guess, answer)` → tuple(GREEN/YELLOW/GRAY)
- `pattern_distribution(candidate, possibilities, feedback_fn)`
- `expected_information_gain(candidate, possibilities, feedback_fn)` = entropy over feedback-pattern distribution
- `best_guess(candidates, possibilities, feedback_fn)` = argmax EIG

Module facade (`InformationTheoryModule`): `entropy`, `surprise`, `entropy_from_counts`,
`joint_entropy`, `conditional_entropy`, `mutual_information`, `kl_divergence`,
`wordle_feedback`, `expected_information_gain`, `best_guess`; lifecycle
`initialize`/`health_check`/`shutdown`; `set_event_bus`. Factory
`create_information_theory_module`.

## Grounding (real transcripts)
- StatQuest YtebGVx-Fxw: surprise = log2(1/p); entropy = expected surprise.
- StatQuest eJIp_mgVLwE: MI(X;Y) = H(X) - H(X|Y) from joint/marginals.
- 3blue1brown v68zYyaEmEA + fRed0Xmc2Wg: expected info gain = entropy over the
  guess's feedback-pattern distribution; choose the max.

## UNVALIDATED
- Full `PlatformOS.initialize()` boot not exercised (registration-only check per task).
- EventBus publishing tested only against a fake bus, not the real kernel bus.
- Wordle solver validated on tiny synthetic word lists, not a full dictionary.
- `wordle_feedback` multiplicity tested loosely (counts gray ≥ 1), not exhaustively.
