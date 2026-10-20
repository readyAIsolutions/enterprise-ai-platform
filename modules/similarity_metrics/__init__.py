"""similarity_metrics — cosine / Pearson / covariance similarity as a module.

Grounded in three StatQuest transcripts (Josh Starmer):

* *Cosine Similarity* (e9U0QAFbfLI) — dot product over the product of
  magnitudes; invariant to vector length; ranges -1..1.
* *Pearson's Correlation* (xZ_z8KWkhXE) — the "centered cosine": cosine
  similarity on mean-centered data, equal to covariance over the product of
  standard deviations.
* *Covariance* (qtaqvPAeEJY) — the mean of products of deviations from the
  mean; its sign gives the relationship direction and underlies correlation.

The deterministic math lives in :mod:`enterprise.modules.similarity_metrics.core`;
this package registers it as a Platform Kernel module with an
initialize / health_check / shutdown lifecycle and a thin facade. It also
exposes a :func:`rank` facade for RAG retrieval ranking.
"""

from __future__ import annotations

import logging
from typing import Optional

from enterprise.platform_kernel import Event, HealthStatus, Module, module

from .core import (
    cosine_similarity,
    covariance,
    dot,
    euclidean_distance,
    magnitude,
    mean,
    pearson_correlation,
    rank,
    std,
    variance,
)

logger = logging.getLogger("eni.similarity_metrics_module")

__version__ = "1.0.0"
__all__ = [
    "SimilarityMetricsModule",
    "create_similarity_metrics_module",
    "cosine_similarity",
    "covariance",
    "dot",
    "euclidean_distance",
    "magnitude",
    "mean",
    "pearson_correlation",
    "rank",
    "std",
    "variance",
]


@module(name="similarity_metrics", version=__version__)
class SimilarityMetricsModule(Module):
    """Kernel module exposing cosine/Pearson/covariance similarity math."""

    def __init__(self, config: Optional[dict] = None) -> None:
        super().__init__(config)
        self._event_bus = None

    async def initialize(self) -> None:
        self._status = HealthStatus.STARTING
        try:
            # Sanity-check the core against a known invariant: cosine of a
            # vector with itself is 1.0.
            _ = cosine_similarity([1.0, 0.0], [1.0, 0.0])
            self._status = HealthStatus.HEALTHY
        except Exception as exc:  # pragma: no cover - defensive
            self._status = HealthStatus.UNHEALTHY
            raise exc

    async def health_check(self) -> HealthStatus:
        return self._status

    async def shutdown(self) -> None:
        self._status = HealthStatus.STOPPING

    # -- facade -------------------------------------------------------------
    def cosine(self, a, b) -> float:
        score = cosine_similarity(a, b)
        self._publish("similarity_metrics.cosine", {"score": score})
        return score

    def pearson(self, a, b) -> float:
        score = pearson_correlation(a, b)
        self._publish("similarity_metrics.pearson", {"score": score})
        return score

    def covariance(self, a, b) -> float:
        return covariance(a, b)

    def variance(self, v) -> float:
        return variance(v)

    def std(self, v) -> float:
        return std(v)

    def dot(self, a, b) -> float:
        return dot(a, b)

    def magnitude(self, v) -> float:
        return magnitude(v)

    def euclidean(self, a, b) -> float:
        return euclidean_distance(a, b)

    def rank(self, query, documents, metric: str = "cosine"):
        results = rank(query, documents, metric=metric)
        self._publish(
            "similarity_metrics.ranked",
            {"metric": metric, "count": len(results)},
        )
        return results

    # -- helpers ------------------------------------------------------------
    def set_event_bus(self, event_bus) -> None:
        """Store the kernel EventBus for cross-module publishing."""
        self._event_bus = event_bus

    def _publish(self, topic: str, payload: dict) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(
                Event.create(topic=topic, source=self.name, payload=payload)
            )


def create_similarity_metrics_module(
    config: Optional[dict] = None,
) -> SimilarityMetricsModule:
    """Factory used for kernel discovery / direct instantiation."""
    return SimilarityMetricsModule(config=config)
