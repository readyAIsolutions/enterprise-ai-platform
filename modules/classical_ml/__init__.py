"""Classical-ML module — stdlib classical machine-learning toolkit.

Grounded in eight real StatQuest transcripts (see ``core`` for the per-algorithm
mapping). The module exposes a network-free, pure-standard-library toolkit:
Multinomial & Gaussian Naive Bayes, a Gini-impurity decision tree, K-means,
K-nearest-neighbours, PCA (power iteration), ROC/AUC, and a bootstrap p-value.

Source video IDs: O2L2Uv9pdDA, H3EjCKtlVog, _L39rN6gz7Y, 4b5d3muPQmA,
HVXime0nQeI, FgakZw6K1QQ, 4jRBRDbJemM, N4ZQQqyIf6k.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from enterprise.platform_kernel import HealthStatus, Module, module

from .core import (  # noqa: F401
    DecisionTreeClassifier,
    GaussianNaiveBayes,
    KMeans,
    KNNClassifier,
    MultinomialNaiveBayes,
    PCA,
    bootstrap_pvalue,
    gini_impurity,
    roc_auc,
)

logger = logging.getLogger("eni.classical_ml")
__version__ = "1.0.0"


@module(
    name="classical_ml",
    version="1.0.0",
    config_defaults={
        "default_knn_k": 3,
        "default_tree_max_depth": 5,
        "default_bootstrap_iters": 10000,
        "nb_alpha": 1.0,
    },
)
class ClassicalMLModule(Module):
    """ENI platform wrapper around the pure-stdlib classical-ML toolkit."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._event_bus: Any = None

    async def initialize(self) -> None:
        try:
            # Smoke-test the toolkit so a broken import surfaces at boot.
            nb = GaussianNaiveBayes()
            nb.fit([[0.0], [10.0]], ["a", "b"])
            assert nb.predict([0.1]) == "a"
            self._status = HealthStatus.HEALTHY
            logger.info("classical_ml module initialized")
        except Exception:
            self._status = HealthStatus.UNHEALTHY
            logger.exception("classical_ml module failed to initialize")
            raise

    async def health_check(self) -> HealthStatus:
        return self._status

    async def shutdown(self) -> None:
        self._status = HealthStatus.STOPPING

    def set_event_bus(self, event_bus: Any) -> None:
        self._event_bus = event_bus

    # ------------------------------------------------------------- facade
    def train_naive_bayes(self, X: Sequence[Sequence[Any]],
                          y: Sequence[str], kind: str = "gaussian"
                          ) -> Any:
        """Train a Naive Bayes classifier ('gaussian' or 'multinomial')."""
        if kind == "gaussian":
            return GaussianNaiveBayes().fit(X, y)
        if kind == "multinomial":
            alpha = float(self._config.get("nb_alpha", 1.0))
            return MultinomialNaiveBayes(alpha=alpha).fit(X, y)
        raise ValueError(f"unknown naive bayes kind: {kind}")

    def fit_decision_tree(self, X: Sequence[Sequence[float]],
                          y: Sequence[str],
                          max_depth: Optional[int] = None
                          ) -> DecisionTreeClassifier:
        """Fit a Gini-impurity decision/classification tree."""
        depth = max_depth or int(self._config.get("default_tree_max_depth", 5))
        return DecisionTreeClassifier(max_depth=depth).fit(X, y)

    def classify_knn(self, X_train: Sequence[Sequence[float]],
                     y_train: Sequence[str], x: Sequence[float],
                     k: Optional[int] = None) -> str:
        """Classify a point by majority vote of its k nearest neighbours."""
        kk = k or int(self._config.get("default_knn_k", 3))
        return KNNClassifier(k=kk).fit(X_train, y_train).predict(x)

    def kmeans(self, X: Sequence[Sequence[float]], k: int,
               seed: Optional[int] = None) -> Dict[str, Any]:
        """Run Lloyd's k-means; return labels, centroids and inertia."""
        model = KMeans(k=k, seed=seed).fit(X)
        return {
            "labels": model.labels_,
            "centroids": model.centroids,
            "inertia": model.inertia_,
        }

    def pca(self, X: Sequence[Sequence[float]], n_components: int = 2,
            seed: int = 0) -> Dict[str, Any]:
        """Project data onto its top principal components."""
        model = PCA(n_components=n_components, seed=seed)
        projected = model.fit_transform(X)
        return {
            "projected": projected,
            "components": model.components_,
            "explained_variance_ratio": model.explained_variance_ratio_,
        }

    def roc_auc(self, y_true: Sequence[int], y_score: Sequence[float]
                ) -> Dict[str, object]:
        """Compute the ROC curve points and AUC."""
        return roc_auc(y_true, y_score)

    def bootstrap_pvalue(self, sample_a: Sequence[float],
                         sample_b: Sequence[float],
                         n_iter: Optional[int] = None,
                         seed: Optional[int] = None) -> Dict[str, float]:
        """Two-sample bootstrap p-value for a difference in means."""
        iters = n_iter or int(self._config.get("default_bootstrap_iters", 10000))
        result = bootstrap_pvalue(sample_a, sample_b, n_iter=iters, seed=seed)
        if self._event_bus is not None:
            try:
                self._event_bus.publish("classical_ml.bootstrap", result)
            except Exception:  # pragma: no cover - event bus is optional
                logger.debug("event bus publish failed", exc_info=True)
        return result


def create_classical_ml_module(
    config: Optional[dict[str, Any]] = None
) -> ClassicalMLModule:
    return ClassicalMLModule(config=config or {})


__all__ = [
    "ClassicalMLModule",
    "create_classical_ml_module",
    "MultinomialNaiveBayes",
    "GaussianNaiveBayes",
    "DecisionTreeClassifier",
    "KMeans",
    "KNNClassifier",
    "PCA",
    "roc_auc",
    "bootstrap_pvalue",
    "gini_impurity",
    "__version__",
]
