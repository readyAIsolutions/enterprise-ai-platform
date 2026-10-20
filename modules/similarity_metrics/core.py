"""Pure, network-free similarity/correlation math (stdlib ``math`` only).

Grounded in three StatQuest transcripts by Josh Starmer:

* *Cosine Similarity* (e9U0QAFbfLI): the cosine similarity between two vectors
  is their dot product divided by the product of their magnitudes. It is
  invariant to vector length (scaling a vector does not change the cosine) and
  ranges from -1 to 1.
* *Pearson's Correlation* (xZ_z8KWkhXE): Pearson correlation is the "centered
  cosine" — it is the cosine similarity computed on mean-centered data, and
  equivalently the covariance divided by the product of the standard deviations.
  It also ranges from -1 to 1.
* *Covariance* (qtaqvPAeEJY): covariance is the mean of the products of the
  deviations from the mean. Its sign indicates the direction of the
  relationship, but its magnitude is scale-dependent, which is why correlation
  normalizes it.

These three are deliberately connected in the transcripts: cosine similarity is
the *uncentered* relationship, Pearson correlation is cosine similarity on
mean-centered vectors, and covariance is the (un-normalized) quantity that sits
under correlation. This module makes that relationship explicit in code.
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

Vector = Sequence[float]


# --------------------------------------------------------------------------- #
# Primitive building blocks
# --------------------------------------------------------------------------- #
def _check_lengths(a: Vector, b: Vector) -> None:
    if len(a) != len(b):
        raise ValueError(
            f"vectors must have the same length, got {len(a)} and {len(b)}"
        )


def dot(a: Vector, b: Vector) -> float:
    """Dot product: sum of element-wise products.

    This is the numerator of cosine similarity in the transcript.
    """
    _check_lengths(a, b)
    return math.fsum(x * y for x, y in zip(a, b))


def magnitude(v: Vector) -> float:
    """Euclidean length (L2 norm) of a vector: sqrt(dot(v, v))."""
    return math.sqrt(math.fsum(x * x for x in v))


def euclidean_distance(a: Vector, b: Vector) -> float:
    """Straight-line distance between two vectors."""
    _check_lengths(a, b)
    return math.sqrt(math.fsum((x - y) ** 2 for x, y in zip(a, b)))


def mean(v: Vector) -> float:
    """Arithmetic mean of the values."""
    if len(v) == 0:
        raise ValueError("mean of an empty vector is undefined")
    return math.fsum(v) / len(v)


# --------------------------------------------------------------------------- #
# Cosine similarity — the uncentered relationship (transcript e9U0QAFbfLI)
# --------------------------------------------------------------------------- #
def cosine_similarity(a: Vector, b: Vector) -> float:
    """Cosine similarity = dot(a, b) / (|a| * |b|).

    Invariant to vector length / scaling, ranges from -1 to 1. Raises on a
    zero vector (undefined magnitude) or on length mismatch.
    """
    _check_lengths(a, b)
    mag_a = magnitude(a)
    mag_b = magnitude(b)
    if mag_a == 0.0 or mag_b == 0.0:
        raise ValueError("cosine similarity is undefined for a zero vector")
    cos = dot(a, b) / (mag_a * mag_b)
    # Guard against tiny floating-point drift outside [-1, 1].
    if cos > 1.0:
        return 1.0
    if cos < -1.0:
        return -1.0
    return cos


# --------------------------------------------------------------------------- #
# Covariance — the quantity under correlation (transcript qtaqvPAeEJY)
# --------------------------------------------------------------------------- #
def covariance(a: Vector, b: Vector) -> float:
    """Population covariance: mean of products of deviations from the mean.

    cov(a, b) = (1/n) * sum((a_i - mean(a)) * (b_i - mean(b))).

    The sign indicates the direction of the relationship (positive => the
    variables move together); the magnitude is scale-dependent.
    """
    _check_lengths(a, b)
    n = len(a)
    if n == 0:
        raise ValueError("covariance of empty vectors is undefined")
    ma = mean(a)
    mb = mean(b)
    return math.fsum((x - ma) * (y - mb) for x, y in zip(a, b)) / n


def variance(v: Vector) -> float:
    """Population variance = covariance of a vector with itself."""
    return covariance(v, v)


def std(v: Vector) -> float:
    """Population standard deviation = sqrt(variance)."""
    return math.sqrt(variance(v))


# --------------------------------------------------------------------------- #
# Pearson correlation — the centered cosine (transcript xZ_z8KWkhXE)
# --------------------------------------------------------------------------- #
def _center(v: Vector) -> List[float]:
    m = mean(v)
    return [x - m for x in v]


def pearson_correlation(a: Vector, b: Vector) -> float:
    """Pearson's correlation coefficient.

    Computed as covariance(a, b) / (std(a) * std(b)). This is mathematically
    identical to the cosine similarity of the mean-centered vectors (the
    "centered cosine" from the transcript). Ranges from -1 to 1. Raises if
    either vector has zero variance (a flat line has no correlation defined).
    """
    _check_lengths(a, b)
    sa = std(a)
    sb = std(b)
    if sa == 0.0 or sb == 0.0:
        raise ValueError(
            "Pearson correlation is undefined when a vector has zero variance"
        )
    r = covariance(a, b) / (sa * sb)
    if r > 1.0:
        return 1.0
    if r < -1.0:
        return -1.0
    return r


# --------------------------------------------------------------------------- #
# RAG retrieval ranking
# --------------------------------------------------------------------------- #
_METRICS = {
    "cosine": cosine_similarity,
    "pearson": pearson_correlation,
    "dot": dot,
    # Euclidean is a distance: smaller is more similar, so we negate it to
    # keep "higher score == more similar" for a uniform sort.
    "euclidean": lambda q, d: -euclidean_distance(q, d),
}


def rank(
    query: Vector,
    documents: Sequence[Vector],
    metric: str = "cosine",
) -> List[Tuple[int, float]]:
    """Rank ``documents`` against ``query`` by similarity, most similar first.

    Returns a list of ``(original_index, score)`` tuples sorted by score
    descending. Useful as a RAG retrieval ranker over embedding vectors.
    """
    if metric not in _METRICS:
        raise ValueError(
            f"unknown metric {metric!r}; choose from {sorted(_METRICS)}"
        )
    fn = _METRICS[metric]
    scored = [(i, float(fn(query, doc))) for i, doc in enumerate(documents)]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored
