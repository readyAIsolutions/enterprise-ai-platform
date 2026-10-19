# STATUS — classical_ml module (Demiurge enterprise boost)

Pure-stdlib classical-ML toolkit for LO's ENI Enterprise Platform, grounded in 8
real StatQuest transcripts. No numpy/pandas/sklearn/scipy — `math` + `random` only.

## PASS/FAIL board

| Check | Result |
|-------|--------|
| `pytest modules/classical_ml/tests -q` | **PASS — 16 passed** |
| Module registration (`classical_ml` in `_MODULE_REGISTRY`) | **PASS — True** |
| Pure stdlib (no banned imports) | **PASS** |
| Async lifecycle (initialize → HEALTHY → shutdown → STOPPING) | **PASS** |

## Algorithms & source video IDs

| Algorithm | What it does | Video ID |
|-----------|-------------|----------|
| `MultinomialNaiveBayes` | Word-histogram NB with Laplace (alpha) smoothing; log-prob classification (spam filter) | O2L2Uv9pdDA |
| `GaussianNaiveBayes` | Per-class/per-feature mean+var, Gaussian log-likelihood + log prior (Troll-2 example) | H3EjCKtlVog |
| `DecisionTreeClassifier` | Recursive binary splits minimising Gini impurity, `max_depth` cap | _L39rN6gz7Y |
| `KMeans` | Lloyd's algorithm, seeded init, inertia, deterministic with seed | 4b5d3muPQmA |
| `KNNClassifier` | Euclidean distance, majority vote, configurable k | HVXime0nQeI |
| `PCA` | Center → covariance matrix → power iteration + deflation → project + explained-variance ratio | FgakZw6K1QQ |
| `roc_auc` | Threshold sweep → FPR/TPR points → trapezoidal AUC | 4jRBRDbJemM |
| `bootstrap_pvalue` | Pool + resample-with-replacement null distribution → two-sided p-value, seeded | N4ZQQqyIf6k |

## Module API

Facade methods on `ClassicalMLModule`: `train_naive_bayes(X, y, kind)`,
`fit_decision_tree(X, y, max_depth)`, `classify_knn(X_train, y_train, x, k)`,
`kmeans(X, k, seed)`, `pca(X, n_components, seed)`, `roc_auc(y_true, y_score)`,
`bootstrap_pvalue(sample_a, sample_b, n_iter, seed)`. Plus lifecycle
(`initialize`/`health_check`/`shutdown`/`set_event_bus`) and factory
`create_classical_ml_module(config)`.

## UNVALIDATED / deliberately skipped

- **`gradient_descent` intentionally NOT implemented** — none of the 8 assigned
  transcripts teach gradient descent, so it was skipped rather than fabricated
  (per task instruction).
- Algorithms validated only on the tiny hand-constructed datasets in the test
  suite; not benchmarked against sklearn or on large/real datasets.
- PCA uses power iteration + deflation (not full Jacobi); accurate for the
  dominant components tested but eigenvectors of near-degenerate covariance
  matrices are not guaranteed.
- Event-bus publish path in `bootstrap_pvalue` is guarded but not exercised by a
  live bus in tests.
