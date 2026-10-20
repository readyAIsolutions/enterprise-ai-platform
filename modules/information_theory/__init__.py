"""information_theory — Shannon entropy, mutual information, KL divergence, and
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
"""

from __future__ import annotations

import logging
from typing import Optional

from enterprise.platform_kernel import Event, HealthStatus, Module, module

from .core import (
    GRAY,
    GREEN,
    YELLOW,
    best_guess,
    conditional_entropy,
    entropy_from_counts,
    expected_information_gain,
    joint_entropy,
    kl_divergence,
    mutual_information,
    pattern_distribution,
    shannon_entropy,
    surprise,
    wordle_feedback,
)

logger = logging.getLogger("eni.information_theory_module")

__version__ = "1.0.0"
__all__ = [
    "InformationTheoryModule",
    "create_information_theory_module",
    "GRAY",
    "GREEN",
    "YELLOW",
    "best_guess",
    "conditional_entropy",
    "entropy_from_counts",
    "expected_information_gain",
    "joint_entropy",
    "kl_divergence",
    "mutual_information",
    "pattern_distribution",
    "shannon_entropy",
    "surprise",
    "wordle_feedback",
]


@module(name="information_theory", version=__version__)
class InformationTheoryModule(Module):
    """Kernel module exposing information-theory primitives and a Wordle solver."""

    def __init__(self, config: Optional[dict] = None) -> None:
        super().__init__(config)
        self._event_bus = None

    async def initialize(self) -> None:
        self._status = HealthStatus.STARTING
        try:
            # Sanity-check the core on a fair coin: entropy must be exactly 1 bit.
            h = shannon_entropy([0.5, 0.5])
            if abs(h - 1.0) > 1e-9:
                raise RuntimeError(f"core self-check failed: fair-coin H={h}")
            self._status = HealthStatus.HEALTHY
        except Exception as exc:
            self._status = HealthStatus.UNHEALTHY
            raise exc

    async def health_check(self) -> HealthStatus:
        return self._status

    async def shutdown(self) -> None:
        self._status = HealthStatus.STOPPING

    # -- facade -------------------------------------------------------------
    def surprise(self, p: float) -> float:
        return surprise(p)

    def entropy(self, probabilities) -> float:
        h = shannon_entropy(probabilities)
        self._publish("information_theory.entropy", {"bits": h})
        return h

    def entropy_from_counts(self, counts) -> float:
        return entropy_from_counts(counts)

    def joint_entropy(self, joint) -> float:
        return joint_entropy(joint)

    def conditional_entropy(self, joint) -> float:
        return conditional_entropy(joint)

    def mutual_information(self, joint) -> float:
        mi = mutual_information(joint)
        self._publish("information_theory.mutual_information", {"bits": mi})
        return mi

    def kl_divergence(self, p, q) -> float:
        return kl_divergence(p, q)

    def wordle_feedback(self, guess, answer):
        return wordle_feedback(guess, answer)

    def expected_information_gain(self, candidate, possibilities, feedback_fn=None) -> float:
        return expected_information_gain(candidate, possibilities, feedback_fn or wordle_feedback)

    def best_guess(self, candidates, possibilities, feedback_fn=None):
        guess = best_guess(candidates, possibilities, feedback_fn or wordle_feedback)
        self._publish("information_theory.best_guess", {"guess": guess})
        return guess

    # -- helpers ------------------------------------------------------------
    def _publish(self, topic: str, payload: dict) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(
                Event.create(topic=topic, source=self.name, payload=payload)
            )

    def set_event_bus(self, event_bus) -> None:
        """Store the kernel EventBus for cross-module publishing."""
        self._event_bus = event_bus


def create_information_theory_module(config: Optional[dict] = None) -> InformationTheoryModule:
    """Factory used for kernel discovery / direct instantiation."""
    return InformationTheoryModule(config=config)
