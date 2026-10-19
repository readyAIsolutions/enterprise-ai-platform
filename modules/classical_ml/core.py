"""Classical-ML toolkit — pure-stdlib implementations of the algorithms taught
in eight real StatQuest transcripts.

Every algorithm here is grounded in a specific StatQuest video:

* **Multinomial Naive Bayes** (``O2L2Uv9pdDA`` — "Naive Bayes, Clearly
  Explained"): build word histograms per class, turn counts into likelihood
  probabilities, apply **Laplace / alpha smoothing** so an unseen word does not
  zero-out a whole message, and classify by the class with the largest
  ``log(prior) + sum(count * log(p(word|class)))`` score (logs avoid underflow).

* **Gaussian Naive Bayes** (``H3EjCKtlVog`` — "Gaussian Naive Bayes"): estimate a
  per-class, per-feature mean and variance, score a new point with the Gaussian
  likelihood, and sum log-likelihoods plus the log prior (the video's Troll-2
  popcorn/soda/candy example).

* **Decision / Classification Tree** (``_L39rN6gz7Y``): recursive binary splits
  chosen to minimise **Gini impurity**, growing to ``max_depth`` or pure leaves.

* **K-means clustering** (``4b5d3muPQmA``): Lloyd's algorithm — pick k initial
  centroids, assign each point to the nearest centroid, recompute centroids,
  repeat; track total within-cluster variation (inertia).

* **K-nearest neighbours** (``HVXime0nQeI``): classify a point by majority vote
  of its k nearest neighbours under Euclidean distance.

* **PCA** (``FgakZw6K1QQ``): center the data, build the covariance matrix,
  extract top eigenvectors by **power iteration with deflation**, project onto
  principal components, report explained-variance ratios.

* **ROC / AUC** (``4jRBRDbJemM``): sweep every classification threshold, plot
  the False-Positive-Rate vs True-Positive-Rate curve, integrate it with the
  trapezoid rule to get the AUC.

* **Bootstrapping p-values** (``N4ZQQqyIf6k``): shift samples to the null,
  resample with replacement many times, and count how often the bootstrapped
  statistic is at least as extreme as the observed one.

Pure standard library only (``math`` + ``random``). Network-free and
deterministic when a seed is supplied.
"""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

Vector = Sequence[float]
Matrix = Sequence[Sequence[float]]


# ===========================================================================
# Multinomial Naive Bayes  (O2L2Uv9pdDA)
# ===========================================================================


class MultinomialNaiveBayes:
    """Multinomial / categorical Naive Bayes with Laplace smoothing.

    Trains on token lists (one list of words per document). Mirrors the
    StatQuest spam-filter example: histogram the words in each class, convert
    to probabilities, add ``alpha`` smoothing so unseen words do not zero the
    product, then classify with summed log-probabilities.
    """

    def __init__(self, alpha: float = 1.0) -> None:
        self.alpha = alpha
        self.vocab: set[str] = set()
        self.class_priors: Dict[str, float] = {}
        self.word_counts: Dict[str, Counter] = {}
        self.class_totals: Dict[str, int] = {}
        self.classes: List[str] = []

    def fit(self, documents: Sequence[Sequence[str]],
            labels: Sequence[str]) -> "MultinomialNaiveBayes":
        if len(documents) != len(labels):
            raise ValueError("documents and labels must be the same length")
        self.word_counts = defaultdict(Counter)
        class_doc_counts: Counter = Counter()
        for tokens, label in zip(documents, labels):
            class_doc_counts[label] += 1
            for tok in tokens:
                self.word_counts[label][tok] += 1
                self.vocab.add(tok)
        self.classes = sorted(class_doc_counts)
        n_docs = sum(class_doc_counts.values())
        self.class_priors = {c: class_doc_counts[c] / n_docs for c in self.classes}
        self.class_totals = {
            c: sum(self.word_counts[c].values()) for c in self.classes
        }
        return self

    def _log_prob_word(self, word: str, label: str) -> float:
        count = self.word_counts[label].get(word, 0)
        numerator = count + self.alpha
        denominator = self.class_totals[label] + self.alpha * len(self.vocab)
        return math.log(numerator / denominator)

    def predict_log_scores(self, tokens: Sequence[str]) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        for c in self.classes:
            score = math.log(self.class_priors[c])
            for tok in tokens:
                if tok in self.vocab:
                    score += self._log_prob_word(tok, c)
            scores[c] = score
        return scores

    def predict(self, tokens: Sequence[str]) -> str:
        scores = self.predict_log_scores(tokens)
        return max(scores, key=lambda c: scores[c])


# ===========================================================================
# Gaussian Naive Bayes  (H3EjCKtlVog)
# ===========================================================================


def _gaussian_log_likelihood(x: float, mean: float, var: float) -> float:
    """Log of the Gaussian (normal) probability density at ``x``."""
    if var <= 0.0:
        var = 1e-9
    return -0.5 * math.log(2.0 * math.pi * var) - ((x - mean) ** 2) / (2.0 * var)


class GaussianNaiveBayes:
    """Gaussian Naive Bayes — per-class, per-feature mean + variance.

    Classifies with ``log(prior) + sum_features log N(x | mean, var)`` which is
    exactly the Troll-2 example (popcorn / soda / candy) from the video, using
    logs so the product of small likelihoods does not underflow.
    """

    def __init__(self) -> None:
        self.classes: List[str] = []
        self.priors: Dict[str, float] = {}
        self.means: Dict[str, List[float]] = {}
        self.variances: Dict[str, List[float]] = {}

    def fit(self, X: Matrix, y: Sequence[str]) -> "GaussianNaiveBayes":
        if len(X) != len(y):
            raise ValueError("X and y must be the same length")
        by_class: Dict[str, List[Sequence[float]]] = defaultdict(list)
        for row, label in zip(X, y):
            by_class[label].append(row)
        self.classes = sorted(by_class)
        n = len(X)
        for c in self.classes:
            rows = by_class[c]
            self.priors[c] = len(rows) / n
            n_feat = len(rows[0])
            means, variances = [], []
            for j in range(n_feat):
                col = [r[j] for r in rows]
                mean = sum(col) / len(col)
                if len(col) > 1:
                    var = sum((v - mean) ** 2 for v in col) / (len(col) - 1)
                else:
                    var = 1e-9
                means.append(mean)
                variances.append(max(var, 1e-9))
            self.means[c] = means
            self.variances[c] = variances
        return self

    def predict_log_scores(self, x: Vector) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        for c in self.classes:
            score = math.log(self.priors[c])
            for j, xj in enumerate(x):
                score += _gaussian_log_likelihood(
                    xj, self.means[c][j], self.variances[c][j]
                )
            scores[c] = score
        return scores

    def predict(self, x: Vector) -> str:
        scores = self.predict_log_scores(x)
        return max(scores, key=lambda c: scores[c])


# ===========================================================================
# Decision / Classification Tree  (_L39rN6gz7Y)
# ===========================================================================


def gini_impurity(labels: Sequence[str]) -> float:
    """Gini impurity of a set of labels (0 == perfectly pure)."""
    if not labels:
        return 0.0
    n = len(labels)
    counts = Counter(labels)
    return 1.0 - sum((c / n) ** 2 for c in counts.values())


class _TreeNode:
    def __init__(self) -> None:
        self.feature: Optional[int] = None
        self.threshold: Optional[float] = None
        self.left: Optional["_TreeNode"] = None
        self.right: Optional["_TreeNode"] = None
        self.prediction: Optional[str] = None


class DecisionTreeClassifier:
    """Binary classification tree using Gini-impurity splits (CART-style).

    Grounded in the StatQuest trees video: for each candidate feature/threshold
    compute the Gini-weighted impurity of the two child groups, keep the split
    with the lowest impurity, and recurse until pure or ``max_depth``.
    """

    def __init__(self, max_depth: int = 5, min_samples_split: int = 2) -> None:
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.root: Optional[_TreeNode] = None

    def fit(self, X: Matrix, y: Sequence[str]) -> "DecisionTreeClassifier":
        self.root = self._build(list(X), list(y), depth=0)
        return self

    def _majority(self, y: Sequence[str]) -> str:
        return Counter(y).most_common(1)[0][0]

    def _best_split(self, X: List[Sequence[float]], y: List[str]
                    ) -> Optional[Tuple[int, float, float]]:
        n_features = len(X[0])
        best_gini = gini_impurity(y)
        best: Optional[Tuple[int, float, float]] = None
        for feature in range(n_features):
            values = sorted({row[feature] for row in X})
            for i in range(len(values) - 1):
                threshold = (values[i] + values[i + 1]) / 2.0
                left_y = [y[j] for j, row in enumerate(X) if row[feature] <= threshold]
                right_y = [y[j] for j, row in enumerate(X) if row[feature] > threshold]
                if not left_y or not right_y:
                    continue
                n = len(y)
                weighted = (
                    len(left_y) / n * gini_impurity(left_y)
                    + len(right_y) / n * gini_impurity(right_y)
                )
                if weighted < best_gini:
                    best_gini = weighted
                    best = (feature, threshold, weighted)
        return best

    def _build(self, X: List[Sequence[float]], y: List[str], depth: int) -> _TreeNode:
        node = _TreeNode()
        if (len(set(y)) == 1 or depth >= self.max_depth
                or len(y) < self.min_samples_split):
            node.prediction = self._majority(y)
            return node
        split = self._best_split(X, y)
        if split is None:
            node.prediction = self._majority(y)
            return node
        feature, threshold, _ = split
        left_idx = [j for j, row in enumerate(X) if row[feature] <= threshold]
        right_idx = [j for j, row in enumerate(X) if row[feature] > threshold]
        node.feature = feature
        node.threshold = threshold
        node.left = self._build([X[j] for j in left_idx],
                                [y[j] for j in left_idx], depth + 1)
        node.right = self._build([X[j] for j in right_idx],
                                 [y[j] for j in right_idx], depth + 1)
        return node

    def _predict_one(self, node: _TreeNode, x: Vector) -> str:
        if node.prediction is not None:
            return node.prediction
        assert node.feature is not None and node.threshold is not None
        if x[node.feature] <= node.threshold:
            return self._predict_one(node.left, x)  # type: ignore[arg-type]
        return self._predict_one(node.right, x)  # type: ignore[arg-type]

    def predict(self, x: Vector) -> str:
        if self.root is None:
            raise RuntimeError("tree is not fitted")
        return self._predict_one(self.root, x)

    def predict_all(self, X: Matrix) -> List[str]:
        return [self.predict(row) for row in X]


# ===========================================================================
# K-means clustering  (4b5d3muPQmA)
# ===========================================================================


def _euclidean(a: Vector, b: Vector) -> float:
    return math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b)))


class KMeans:
    """Lloyd's algorithm for k-means clustering (deterministic with a seed).

    Follows the StatQuest recipe: pick k initial points, assign each point to
    the nearest cluster, recompute cluster centres as the mean of their members,
    and repeat until assignments stop changing. ``inertia_`` is the total
    within-cluster variation the video uses to compare clusterings.
    """

    def __init__(self, k: int, max_iter: int = 100, seed: Optional[int] = None) -> None:
        self.k = k
        self.max_iter = max_iter
        self.seed = seed
        self.centroids: List[List[float]] = []
        self.labels_: List[int] = []
        self.inertia_: float = 0.0

    def fit(self, X: Matrix) -> "KMeans":
        rng = random.Random(self.seed)
        points = [list(row) for row in X]
        if self.k > len(points):
            raise ValueError("k cannot exceed number of points")
        # Seeded init: sample k distinct starting points.
        self.centroids = [list(c) for c in rng.sample(points, self.k)]
        labels = [0] * len(points)
        for _ in range(self.max_iter):
            new_labels = []
            for p in points:
                dists = [_euclidean(p, c) for c in self.centroids]
                new_labels.append(dists.index(min(dists)))
            if new_labels == labels:
                labels = new_labels
                break
            labels = new_labels
            for ci in range(self.k):
                members = [points[i] for i in range(len(points)) if labels[i] == ci]
                if members:
                    n_feat = len(members[0])
                    self.centroids[ci] = [
                        sum(m[j] for m in members) / len(members)
                        for j in range(n_feat)
                    ]
        self.labels_ = labels
        self.inertia_ = sum(
            _euclidean(points[i], self.centroids[labels[i]]) ** 2
            for i in range(len(points))
        )
        return self

    def predict(self, x: Vector) -> int:
        dists = [_euclidean(x, c) for c in self.centroids]
        return dists.index(min(dists))


# ===========================================================================
# K-nearest neighbours  (HVXime0nQeI)
# ===========================================================================


class KNNClassifier:
    """K-nearest-neighbours classifier (Euclidean distance, majority vote)."""

    def __init__(self, k: int = 3) -> None:
        self.k = k
        self.X: List[Sequence[float]] = []
        self.y: List[str] = []

    def fit(self, X: Matrix, y: Sequence[str]) -> "KNNClassifier":
        self.X = list(X)
        self.y = list(y)
        return self

    def predict(self, x: Vector) -> str:
        distances = sorted(
            range(len(self.X)), key=lambda i: _euclidean(x, self.X[i])
        )
        nearest = distances[: self.k]
        votes = Counter(self.y[i] for i in nearest)
        return votes.most_common(1)[0][0]

    def predict_all(self, X: Matrix) -> List[str]:
        return [self.predict(row) for row in X]


# ===========================================================================
# PCA  (FgakZw6K1QQ)
# ===========================================================================


def _covariance_matrix(centered: List[List[float]]) -> List[List[float]]:
    n = len(centered)
    n_feat = len(centered[0])
    cov = [[0.0] * n_feat for _ in range(n_feat)]
    denom = max(n - 1, 1)
    for i in range(n_feat):
        for j in range(n_feat):
            cov[i][j] = sum(centered[r][i] * centered[r][j]
                            for r in range(n)) / denom
    return cov


def _mat_vec(mat: List[List[float]], vec: List[float]) -> List[float]:
    return [sum(mat[i][j] * vec[j] for j in range(len(vec)))
            for i in range(len(mat))]


def _normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


def _power_iteration(mat: List[List[float]], n_iter: int = 500,
                     seed: int = 0) -> Tuple[float, List[float]]:
    """Dominant eigenvalue/eigenvector via power iteration."""
    rng = random.Random(seed)
    n = len(mat)
    vec = _normalize([rng.random() + 0.1 for _ in range(n)])
    eigenvalue = 0.0
    for _ in range(n_iter):
        new_vec = _mat_vec(mat, vec)
        new_vec = _normalize(new_vec)
        # Rayleigh quotient estimate of the eigenvalue.
        mv = _mat_vec(mat, new_vec)
        eigenvalue = sum(new_vec[i] * mv[i] for i in range(n))
        if all(abs(new_vec[i] - vec[i]) < 1e-12 for i in range(n)):
            vec = new_vec
            break
        vec = new_vec
    return eigenvalue, vec


def _deflate(mat: List[List[float]], eigenvalue: float,
             eigenvector: List[float]) -> List[List[float]]:
    n = len(mat)
    return [
        [mat[i][j] - eigenvalue * eigenvector[i] * eigenvector[j]
         for j in range(n)]
        for i in range(n)
    ]


class PCA:
    """Principal Component Analysis via power iteration + deflation.

    Grounded in the StatQuest PCA video: center the data on the origin, compute
    the covariance matrix, find the principal-component directions
    (eigenvectors, largest variance first), project the data onto the top
    components, and report each component's share of the total variance.
    """

    def __init__(self, n_components: int = 2, seed: int = 0) -> None:
        self.n_components = n_components
        self.seed = seed
        self.mean_: List[float] = []
        self.components_: List[List[float]] = []
        self.explained_variance_: List[float] = []
        self.explained_variance_ratio_: List[float] = []

    def fit(self, X: Matrix) -> "PCA":
        rows = [list(r) for r in X]
        n_feat = len(rows[0])
        self.mean_ = [sum(r[j] for r in rows) / len(rows) for j in range(n_feat)]
        centered = [[r[j] - self.mean_[j] for j in range(n_feat)] for r in rows]
        cov = _covariance_matrix(centered)
        total_var = sum(cov[i][i] for i in range(n_feat))
        k = min(self.n_components, n_feat)
        self.components_ = []
        self.explained_variance_ = []
        work = [row[:] for row in cov]
        for comp in range(k):
            eigenvalue, eigenvector = _power_iteration(work, seed=self.seed + comp)
            self.components_.append(eigenvector)
            self.explained_variance_.append(eigenvalue)
            work = _deflate(work, eigenvalue, eigenvector)
        self.explained_variance_ratio_ = [
            ev / total_var if total_var else 0.0
            for ev in self.explained_variance_
        ]
        return self

    def transform(self, X: Matrix) -> List[List[float]]:
        out = []
        for r in X:
            centered = [r[j] - self.mean_[j] for j in range(len(self.mean_))]
            out.append([
                sum(centered[j] * comp[j] for j in range(len(comp)))
                for comp in self.components_
            ])
        return out

    def fit_transform(self, X: Matrix) -> List[List[float]]:
        return self.fit(X).transform(X)


# ===========================================================================
# ROC / AUC  (4jRBRDbJemM)
# ===========================================================================


def roc_auc(y_true: Sequence[int], y_score: Sequence[float]
            ) -> Dict[str, object]:
    """Compute ROC curve points and AUC (trapezoidal integration).

    Grounded in the StatQuest ROC/AUC video: sweep every threshold, compute the
    False-Positive-Rate (x) and True-Positive-Rate (y) at each, then integrate
    the resulting curve to get the Area Under the Curve. A perfect, perfectly
    separable ranking yields AUC == 1.0.
    """
    if len(y_true) != len(y_score):
        raise ValueError("y_true and y_score must be the same length")
    positives = sum(1 for t in y_true if t == 1)
    negatives = len(y_true) - positives
    if positives == 0 or negatives == 0:
        raise ValueError("need at least one positive and one negative label")
    # Thresholds: descend through every unique score (plus +inf start).
    thresholds = sorted(set(y_score), reverse=True)
    points: List[Tuple[float, float]] = [(0.0, 0.0)]
    for thr in thresholds:
        tp = sum(1 for t, s in zip(y_true, y_score) if s >= thr and t == 1)
        fp = sum(1 for t, s in zip(y_true, y_score) if s >= thr and t == 0)
        tpr = tp / positives
        fpr = fp / negatives
        points.append((fpr, tpr))
    if points[-1] != (1.0, 1.0):
        points.append((1.0, 1.0))
    # Trapezoidal integration over fpr (x axis).
    points.sort(key=lambda p: (p[0], p[1]))
    auc = 0.0
    for i in range(1, len(points)):
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        auc += (x1 - x0) * (y0 + y1) / 2.0
    return {
        "fpr": [p[0] for p in points],
        "tpr": [p[1] for p in points],
        "thresholds": thresholds,
        "auc": auc,
    }


# ===========================================================================
# Bootstrapping p-values  (N4ZQQqyIf6k)
# ===========================================================================


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def bootstrap_pvalue(sample_a: Sequence[float], sample_b: Sequence[float],
                     n_iter: int = 10000, seed: Optional[int] = None
                     ) -> Dict[str, float]:
    """Two-sample bootstrap p-value for a difference in means.

    Grounded in the StatQuest bootstrapping video: under the null hypothesis the
    two groups come from the same distribution. We pool the samples, then build
    a null distribution by repeatedly resampling (with replacement) two groups
    of the original sizes and recording the difference in means. The two-sided
    p-value is the fraction of bootstrapped differences at least as extreme as
    the observed difference.
    """
    rng = random.Random(seed)
    observed = _mean(sample_a) - _mean(sample_b)
    pooled = list(sample_a) + list(sample_b)
    na, nb = len(sample_a), len(sample_b)
    count_extreme = 0
    for _ in range(n_iter):
        resample_a = [rng.choice(pooled) for _ in range(na)]
        resample_b = [rng.choice(pooled) for _ in range(nb)]
        diff = _mean(resample_a) - _mean(resample_b)
        if abs(diff) >= abs(observed):
            count_extreme += 1
    p_value = (count_extreme + 1) / (n_iter + 1)
    return {
        "observed_diff": observed,
        "p_value": p_value,
        "n_iter": float(n_iter),
    }
