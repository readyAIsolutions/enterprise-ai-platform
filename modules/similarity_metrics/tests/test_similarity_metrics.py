"""Tests for the similarity_metrics module.

Values are grounded in the StatQuest transcripts on cosine similarity,
Pearson correlation, and covariance.
"""

from __future__ import annotations

import math

import pytest

from enterprise.modules.similarity_metrics import (
    SimilarityMetricsModule,
    cosine_similarity,
    covariance,
    create_similarity_metrics_module,
    dot,
    euclidean_distance,
    magnitude,
    mean,
    pearson_correlation,
    rank,
    std,
    variance,
)


# --------------------------------------------------------------------------- #
# Cosine similarity
# --------------------------------------------------------------------------- #
def test_cosine_identical_vectors_is_one():
    assert math.isclose(cosine_similarity([1, 0], [1, 0]), 1.0)


def test_cosine_orthogonal_is_zero():
    assert math.isclose(cosine_similarity([1, 0], [0, 1]), 0.0, abs_tol=1e-12)


def test_cosine_opposite_is_minus_one():
    assert math.isclose(cosine_similarity([1, 0], [-1, 0]), -1.0)


def test_cosine_invariant_to_scaling():
    # Scaling a vector does not change its direction, so cosine == 1.0.
    assert math.isclose(cosine_similarity([1, 2], [2, 4]), 1.0)


def test_cosine_zero_vector_raises():
    with pytest.raises(ValueError):
        cosine_similarity([0, 0], [1, 1])


def test_cosine_length_mismatch_raises():
    with pytest.raises(ValueError):
        cosine_similarity([1, 2, 3], [1, 2])


# --------------------------------------------------------------------------- #
# Covariance / variance / std
# --------------------------------------------------------------------------- #
def test_covariance_positive_for_positively_correlated():
    cov = covariance([1, 2, 3], [1, 2, 3])
    assert cov > 0.0


def test_covariance_negative_for_inversely_related():
    cov = covariance([1, 2, 3], [3, 2, 1])
    assert cov < 0.0


def test_variance_matches_known_value():
    # Population variance of [1,2,3]: mean=2, deviations squared mean = 2/3.
    assert math.isclose(variance([1, 2, 3]), 2.0 / 3.0)


def test_std_is_sqrt_variance():
    assert math.isclose(std([1, 2, 3]), math.sqrt(2.0 / 3.0))


# --------------------------------------------------------------------------- #
# Pearson correlation == cosine of mean-centered vectors
# --------------------------------------------------------------------------- #
def test_pearson_equals_cosine_of_centered_vectors():
    a = [1.0, 2.0, 3.0, 4.0]
    b = [2.0, 1.0, 4.0, 3.0]
    r = pearson_correlation(a, b)
    ma = mean(a)
    mb = mean(b)
    ac = [x - ma for x in a]
    bc = [y - mb for y in b]
    cos_centered = cosine_similarity(ac, bc)
    assert math.isclose(r, cos_centered, rel_tol=1e-9, abs_tol=1e-12)


def test_pearson_perfect_positive():
    assert math.isclose(pearson_correlation([1, 2, 3], [2, 4, 6]), 1.0)


def test_pearson_perfect_negative():
    assert math.isclose(pearson_correlation([1, 2, 3], [6, 4, 2]), -1.0)


def test_pearson_zero_variance_raises():
    with pytest.raises(ValueError):
        pearson_correlation([1, 1, 1], [1, 2, 3])


# --------------------------------------------------------------------------- #
# Primitives
# --------------------------------------------------------------------------- #
def test_dot_known_value():
    assert math.isclose(dot([1, 2, 3], [4, 5, 6]), 32.0)


def test_magnitude_known_value():
    assert math.isclose(magnitude([3, 4]), 5.0)


def test_euclidean_distance_known_value():
    assert math.isclose(euclidean_distance([0, 0], [3, 4]), 5.0)


# --------------------------------------------------------------------------- #
# RAG ranking
# --------------------------------------------------------------------------- #
def test_rank_returns_most_similar_first():
    query = [1.0, 0.0]
    docs = [
        [0.0, 1.0],   # orthogonal  -> cosine 0
        [1.0, 0.1],   # near-aligned -> cosine ~1
        [-1.0, 0.0],  # opposite    -> cosine -1
    ]
    ranked = rank(query, docs, metric="cosine")
    assert ranked[0][0] == 1
    assert ranked[-1][0] == 2


def test_rank_scores_sorted_descending():
    query = [1.0, 0.0]
    docs = [[0.0, 1.0], [1.0, 0.1], [-1.0, 0.0]]
    ranked = rank(query, docs, metric="cosine")
    scores = [s for _, s in ranked]
    assert scores == sorted(scores, reverse=True)


def test_rank_unknown_metric_raises():
    with pytest.raises(ValueError):
        rank([1, 0], [[1, 0]], metric="nope")


# --------------------------------------------------------------------------- #
# Module lifecycle + registration
# --------------------------------------------------------------------------- #
async def test_module_lifecycle():
    from enterprise.platform_kernel import HealthStatus

    mod = create_similarity_metrics_module()
    assert isinstance(mod, SimilarityMetricsModule)
    await mod.initialize()
    status = await mod.health_check()
    assert status == HealthStatus.HEALTHY
    await mod.shutdown()
    assert mod.status == HealthStatus.STOPPING


async def test_module_facade_cosine():
    mod = create_similarity_metrics_module()
    await mod.initialize()
    assert math.isclose(mod.cosine([1, 0], [1, 0]), 1.0)


def test_registration():
    from enterprise.platform_kernel import _MODULE_REGISTRY

    assert "similarity_metrics" in _MODULE_REGISTRY
