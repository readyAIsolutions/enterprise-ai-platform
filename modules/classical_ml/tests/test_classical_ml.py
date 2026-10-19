"""Unit tests for the classical_ml module (network-free, deterministic).

Tiny hand-constructed datasets with known answers verify each algorithm, plus
the async module lifecycle.
"""
from __future__ import annotations

from enterprise.platform_kernel import HealthStatus
from enterprise.modules.classical_ml import (
    DecisionTreeClassifier,
    GaussianNaiveBayes,
    KMeans,
    KNNClassifier,
    MultinomialNaiveBayes,
    PCA,
    bootstrap_pvalue,
    create_classical_ml_module,
    gini_impurity,
    roc_auc,
)


# --------------------------------------------------------------------------
# Multinomial Naive Bayes
# --------------------------------------------------------------------------


def test_multinomial_nb_spam_filter():
    docs = [
        ["dear", "friend", "lunch"],
        ["hello", "friend", "dinner"],
        ["money", "prize", "winner"],
        ["money", "money", "free", "prize"],
    ]
    labels = ["normal", "normal", "spam", "spam"]
    nb = MultinomialNaiveBayes(alpha=1.0).fit(docs, labels)
    assert nb.predict(["money", "prize"]) == "spam"
    assert nb.predict(["dear", "friend"]) == "normal"


def test_multinomial_nb_smoothing_handles_unseen_word():
    nb = MultinomialNaiveBayes(alpha=1.0).fit(
        [["a", "b"], ["c", "d"]], ["x", "y"]
    )
    # An unseen word must not raise / produce -inf.
    scores = nb.predict_log_scores(["zzz", "a"])
    assert all(s > float("-inf") for s in scores.values())


# --------------------------------------------------------------------------
# Gaussian Naive Bayes
# --------------------------------------------------------------------------


def test_gaussian_nb_separable():
    X = [[24.0, 10.0], [23.0, 11.0], [25.0, 9.0],
         [4.0, 2.0], [5.0, 3.0], [3.0, 1.0]]
    y = ["loves", "loves", "loves", "hates", "hates", "hates"]
    gnb = GaussianNaiveBayes().fit(X, y)
    assert gnb.predict([24.0, 10.0]) == "loves"
    assert gnb.predict([4.0, 2.0]) == "hates"
    # 100% train accuracy
    assert all(gnb.predict(row) == label for row, label in zip(X, y))


# --------------------------------------------------------------------------
# Decision tree
# --------------------------------------------------------------------------


def test_gini_impurity_pure_and_mixed():
    assert gini_impurity(["a", "a", "a"]) == 0.0
    assert abs(gini_impurity(["a", "b"]) - 0.5) < 1e-9


def test_decision_tree_perfect_train_accuracy():
    X = [[0.0, 0.0], [0.1, 0.1], [5.0, 5.0], [5.1, 4.9]]
    y = ["lo", "lo", "hi", "hi"]
    tree = DecisionTreeClassifier(max_depth=3).fit(X, y)
    assert tree.predict_all(X) == y
    assert tree.predict([0.05, 0.05]) == "lo"
    assert tree.predict([5.05, 5.05]) == "hi"


# --------------------------------------------------------------------------
# K-means
# --------------------------------------------------------------------------


def test_kmeans_recovers_two_blobs():
    X = [[0.0, 0.0], [0.5, 0.2], [0.1, 0.4],
         [10.0, 10.0], [10.5, 9.8], [9.7, 10.2]]
    km = KMeans(k=2, seed=42).fit(X)
    # The first three and last three points must share clusters respectively.
    assert len(set(km.labels_[:3])) == 1
    assert len(set(km.labels_[3:])) == 1
    assert km.labels_[0] != km.labels_[3]
    assert km.inertia_ < 5.0


def test_kmeans_deterministic_with_seed():
    X = [[0.0], [1.0], [10.0], [11.0]]
    a = KMeans(k=2, seed=7).fit(X)
    b = KMeans(k=2, seed=7).fit(X)
    assert a.labels_ == b.labels_


# --------------------------------------------------------------------------
# KNN
# --------------------------------------------------------------------------


def test_knn_majority_vote():
    X = [[0.0, 0.0], [0.2, 0.1], [5.0, 5.0], [5.1, 4.8]]
    y = ["A", "A", "B", "B"]
    knn = KNNClassifier(k=3).fit(X, y)
    assert knn.predict([0.1, 0.1]) == "A"
    assert knn.predict([5.0, 4.9]) == "B"


# --------------------------------------------------------------------------
# PCA
# --------------------------------------------------------------------------


def test_pca_first_component_aligns_with_major_axis():
    # Data stretched along the x-axis -> PC1 should be ~ (1, 0).
    X = [[-4.0, 0.1], [-2.0, -0.1], [0.0, 0.0], [2.0, 0.1], [4.0, -0.1]]
    pca = PCA(n_components=2, seed=0).fit(X)
    pc1 = pca.components_[0]
    assert abs(abs(pc1[0]) - 1.0) < 0.05
    assert abs(pc1[1]) < 0.1
    # First component explains the vast majority of variance.
    assert pca.explained_variance_ratio_[0] > 0.95


# --------------------------------------------------------------------------
# ROC / AUC
# --------------------------------------------------------------------------


def test_roc_auc_perfect_separation():
    y_true = [0, 0, 1, 1]
    y_score = [0.1, 0.2, 0.8, 0.9]
    result = roc_auc(y_true, y_score)
    assert abs(result["auc"] - 1.0) < 1e-9


def test_roc_auc_random_is_half():
    y_true = [0, 1, 0, 1]
    y_score = [0.5, 0.5, 0.5, 0.5]
    result = roc_auc(y_true, y_score)
    assert abs(result["auc"] - 0.5) < 1e-9


# --------------------------------------------------------------------------
# Bootstrap p-value
# --------------------------------------------------------------------------


def test_bootstrap_pvalue_different_samples_small():
    a = [10.0, 11.0, 12.0, 10.5, 11.5]
    b = [1.0, 0.5, 1.5, 0.8, 1.2]
    result = bootstrap_pvalue(a, b, n_iter=2000, seed=1)
    assert result["p_value"] < 0.05
    assert result["observed_diff"] > 0


def test_bootstrap_pvalue_identical_samples_large():
    a = [5.0, 5.0, 5.0, 5.0]
    b = [5.0, 5.0, 5.0, 5.0]
    result = bootstrap_pvalue(a, b, n_iter=1000, seed=3)
    assert result["p_value"] > 0.5


def test_bootstrap_pvalue_deterministic():
    a = [1.0, 2.0, 3.0]
    b = [4.0, 5.0, 6.0]
    r1 = bootstrap_pvalue(a, b, n_iter=500, seed=9)
    r2 = bootstrap_pvalue(a, b, n_iter=500, seed=9)
    assert r1["p_value"] == r2["p_value"]


# --------------------------------------------------------------------------
# Async module lifecycle
# --------------------------------------------------------------------------


async def test_module_lifecycle():
    mod = create_classical_ml_module()
    await mod.initialize()
    assert await mod.health_check() == HealthStatus.HEALTHY
    await mod.shutdown()
    assert mod.status == HealthStatus.STOPPING


async def test_module_facade_methods():
    mod = create_classical_ml_module()
    await mod.initialize()
    # KNN facade
    assert mod.classify_knn([[0.0], [10.0]], ["a", "b"], [0.1], k=1) == "a"
    # kmeans facade
    km = mod.kmeans([[0.0], [1.0], [10.0], [11.0]], k=2, seed=1)
    assert len(km["centroids"]) == 2
    # roc_auc facade
    assert abs(mod.roc_auc([0, 1], [0.1, 0.9])["auc"] - 1.0) < 1e-9
    # tree facade
    tree = mod.fit_decision_tree([[0.0], [9.0]], ["x", "y"])
    assert tree.predict([0.0]) == "x"
    await mod.shutdown()
