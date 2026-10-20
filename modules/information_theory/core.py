"""information_theory.core — pure, network-free information-theory primitives.

Grounded in real source transcripts:

* StatQuest, *"Entropy (for data science) Clearly Explained!!!"*
  (https://www.youtube.com/watch?v=YtebGVx-Fxw): surprise is the log of the
  inverse of the probability -- ``surprise = log2(1 / p) = -log2(p)`` -- and
  **entropy is the expected (average) surprise**,
  ``H = sum(p * log2(1 / p))``. A certain outcome (p=1) has zero surprise; rare
  outcomes carry more surprise. Log base two is customary.

* StatQuest, *"Mutual Information Clearly Explained!!!"*
  (https://www.youtube.com/watch?v=eJIp_mgVLwE): mutual information measures how
  much knowing one variable reduces the surprise (uncertainty) about another,
  ``MI(X;Y) = H(X) - H(X|Y)``, computed from a joint distribution and its
  marginals. Independent variables share ~0 bits.

* 3blue1brown, *"Solving Wordle using information theory"*
  (https://www.youtube.com/watch?v=v68zYyaEmEA) and its follow-up
  (https://www.youtube.com/watch?v=fRed0Xmc2Wg): the expected information gained
  from a guess is the entropy of the distribution over feedback patterns that
  the guess induces across the remaining possibilities. Pick the guess that
  maximises that expected information gain.

Pure stdlib (``math`` only). No numpy/pandas, no network.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Callable, Dict, Hashable, Iterable, List, Sequence, Tuple

# Numeric tolerance used when checking that a probability vector sums to 1.
_PROB_SUM_TOL = 1e-9

# ---------------------------------------------------------------------------
# Surprise & entropy  (StatQuest: YtebGVx-Fxw)
# ---------------------------------------------------------------------------


def surprise(p: float) -> float:
    """Shannon surprise (self-information) of an outcome with probability ``p``.

    ``surprise = log2(1 / p) = -log2(p)`` (StatQuest). A certain outcome
    (``p == 1``) has zero surprise; the rarer the outcome the larger the value.
    """
    if not (0.0 < p <= 1.0):
        raise ValueError(f"probability must be in (0, 1], got {p!r}")
    return -math.log2(p)


def shannon_entropy(probabilities: Sequence[float]) -> float:
    """Entropy = expected surprise, ``H = sum(p * log2(1 / p))`` in bits.

    Zero-probability outcomes are filtered out (they contribute nothing, and
    ``log2(0)`` is undefined). The non-zero probabilities must sum to ~1.
    """
    probs = [float(p) for p in probabilities]
    for p in probs:
        if p < 0.0:
            raise ValueError(f"probabilities must be non-negative, got {p!r}")
    total = math.fsum(probs)
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"probabilities must sum to ~1.0, got {total!r}")
    nonzero = [p for p in probs if p > 0.0]
    return math.fsum(p * -math.log2(p) for p in nonzero)


def entropy_from_counts(counts: Iterable[float]) -> float:
    """Entropy of an empirical distribution given raw (non-negative) counts."""
    counts = [float(c) for c in counts]
    for c in counts:
        if c < 0.0:
            raise ValueError(f"counts must be non-negative, got {c!r}")
    total = math.fsum(counts)
    if total <= 0.0:
        return 0.0
    return shannon_entropy([c / total for c in counts])


# ---------------------------------------------------------------------------
# Joint distributions: conditional entropy & mutual information
# (StatQuest: eJIp_mgVLwE)
# ---------------------------------------------------------------------------

Joint = Dict[Tuple[Hashable, Hashable], float]


def _normalise_joint(joint: Joint) -> Joint:
    """Validate a joint P(x, y) dict and normalise it to sum to 1."""
    if not joint:
        raise ValueError("joint distribution must be non-empty")
    cleaned: Joint = {}
    for key, val in joint.items():
        if not (isinstance(key, tuple) and len(key) == 2):
            raise ValueError(f"joint keys must be (x, y) tuples, got {key!r}")
        v = float(val)
        if v < 0.0:
            raise ValueError(f"joint probabilities must be non-negative, got {v!r}")
        cleaned[key] = v
    total = math.fsum(cleaned.values())
    if total <= 0.0:
        raise ValueError("joint distribution must have positive total mass")
    return {k: v / total for k, v in cleaned.items()}


def _marginals(joint: Joint) -> Tuple[Dict[Hashable, float], Dict[Hashable, float]]:
    """Return (P(x), P(y)) marginals from a normalised joint."""
    px: Dict[Hashable, float] = {}
    py: Dict[Hashable, float] = {}
    for (x, y), p in joint.items():
        px[x] = px.get(x, 0.0) + p
        py[y] = py.get(y, 0.0) + p
    return px, py


def joint_entropy(joint: Joint) -> float:
    """H(X, Y) of a joint distribution (bits)."""
    j = _normalise_joint(joint)
    return math.fsum(p * -math.log2(p) for p in j.values() if p > 0.0)


def conditional_entropy(joint: Joint) -> float:
    """H(X | Y) = H(X, Y) - H(Y) in bits.

    The average remaining surprise about X once Y is known.
    """
    j = _normalise_joint(joint)
    _, py = _marginals(j)
    h_xy = math.fsum(p * -math.log2(p) for p in j.values() if p > 0.0)
    h_y = math.fsum(p * -math.log2(p) for p in py.values() if p > 0.0)
    return h_xy - h_y


def mutual_information(joint: Joint) -> float:
    """MI(X; Y) = H(X) - H(X | Y)  (StatQuest), equivalently
    ``sum P(x,y) * log2( P(x,y) / (P(x) P(y)) )``.

    Zero for independent variables; non-negative in general.
    """
    j = _normalise_joint(joint)
    px, py = _marginals(j)
    mi = 0.0
    for (x, y), pxy in j.items():
        if pxy <= 0.0:
            continue
        mi += pxy * math.log2(pxy / (px[x] * py[y]))
    # Clamp tiny negative values from floating point noise.
    if -1e-12 < mi < 0.0:
        mi = 0.0
    return mi


# ---------------------------------------------------------------------------
# Kullback-Leibler divergence
# ---------------------------------------------------------------------------


def kl_divergence(p: Sequence[float], q: Sequence[float]) -> float:
    """KL(p || q) = sum p * log2(p / q) in bits.

    Measures the extra surprise from using q to describe outcomes drawn from p.
    KL(p || p) == 0. Requires q[i] > 0 wherever p[i] > 0 (absolute continuity).
    """
    p = [float(x) for x in p]
    q = [float(x) for x in q]
    if len(p) != len(q):
        raise ValueError("p and q must have the same length")
    for dist, name in ((p, "p"), (q, "q")):
        if any(x < 0.0 for x in dist):
            raise ValueError(f"{name} must be non-negative")
        if abs(math.fsum(dist) - 1.0) > 1e-6:
            raise ValueError(f"{name} must sum to ~1.0")
    total = 0.0
    for pi, qi in zip(p, q):
        if pi == 0.0:
            continue
        if qi <= 0.0:
            raise ValueError("q must be > 0 wherever p > 0 (KL undefined)")
        total += pi * math.log2(pi / qi)
    if -1e-12 < total < 0.0:
        total = 0.0
    return total


# ---------------------------------------------------------------------------
# Wordle-style expected information gain  (3blue1brown: v68zYyaEmEA / fRed0Xmc2Wg)
# ---------------------------------------------------------------------------

# Feedback tokens for a Wordle-style comparison.
GREEN = "green"   # right letter, right spot
YELLOW = "yellow"  # right letter, wrong spot
GRAY = "gray"     # letter not present (accounting for multiplicity)

Pattern = Tuple[str, ...]
FeedbackFn = Callable[[str, str], Pattern]


def wordle_feedback(guess: str, answer: str) -> Pattern:
    """Deterministic Wordle feedback pattern for ``guess`` against ``answer``.

    Returns a tuple of per-position tokens (GREEN/YELLOW/GRAY). Handles letter
    multiplicity the way Wordle does: greens are assigned first, then yellows
    only while unmatched copies of a letter remain in the answer.
    """
    if len(guess) != len(answer):
        raise ValueError("guess and answer must be the same length")
    result: List[str] = [GRAY] * len(guess)
    remaining = Counter(answer)
    # First pass: greens.
    for i, (g, a) in enumerate(zip(guess, answer)):
        if g == a:
            result[i] = GREEN
            remaining[g] -= 1
    # Second pass: yellows / grays.
    for i, g in enumerate(guess):
        if result[i] == GREEN:
            continue
        if remaining.get(g, 0) > 0:
            result[i] = YELLOW
            remaining[g] -= 1
    return tuple(result)


def pattern_distribution(
    candidate: str,
    possibilities: Sequence[str],
    feedback_fn: FeedbackFn = wordle_feedback,
) -> Dict[Pattern, int]:
    """Count how many possibilities fall into each feedback pattern bucket."""
    buckets: Counter = Counter()
    for answer in possibilities:
        buckets[feedback_fn(candidate, answer)] += 1
    return dict(buckets)


def expected_information_gain(
    candidate: str,
    possibilities: Sequence[str],
    feedback_fn: FeedbackFn = wordle_feedback,
) -> float:
    """Expected information gain (bits) of guessing ``candidate``.

    3blue1brown: the information a guess yields is the entropy of the
    distribution over the feedback patterns it produces across the remaining
    possibilities. Each pattern has probability ``count / N``; the expected gain
    is ``sum p * log2(1 / p)`` -- i.e. the entropy of that bucket distribution.
    """
    if not possibilities:
        return 0.0
    buckets = pattern_distribution(candidate, possibilities, feedback_fn)
    return entropy_from_counts(buckets.values())


def best_guess(
    candidates: Sequence[str],
    possibilities: Sequence[str],
    feedback_fn: FeedbackFn = wordle_feedback,
) -> str:
    """Return the candidate with the maximum expected information gain.

    Ties are broken deterministically by preferring a candidate that is itself
    still a possibility, then by lexical order.
    """
    if not candidates:
        raise ValueError("candidates must be non-empty")
    poss_set = set(possibilities)

    best = candidates[0]
    best_key = (
        expected_information_gain(best, possibilities, feedback_fn),
        1 if best in poss_set else 0,
        -ord(best[0]) if best else 0,
    )
    for c in candidates[1:]:
        eig = expected_information_gain(c, possibilities, feedback_fn)
        key = (eig, 1 if c in poss_set else 0, -ord(c[0]) if c else 0)
        if key > best_key:
            best_key = key
            best = c
    return best


__all__ = [
    "GREEN",
    "YELLOW",
    "GRAY",
    "surprise",
    "shannon_entropy",
    "entropy_from_counts",
    "joint_entropy",
    "conditional_entropy",
    "mutual_information",
    "kl_divergence",
    "wordle_feedback",
    "pattern_distribution",
    "expected_information_gain",
    "best_guess",
]
