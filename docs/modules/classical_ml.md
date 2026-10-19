# Module: `classical_ml`

- Category: Legacy Core · priority 19
- Version: 1.0.0
- Purpose: Classical-ML module — stdlib classical machine-learning toolkit.
- Skill: `eni-module-classical_ml` (ICM stages) in skills_pack/skills/eni-modules/classical_ml/

## What it does
Classical-ML module — stdlib classical machine-learning toolkit.

Grounded in eight real StatQuest transcripts (see ``core`` for the per-algorithm
mapping). The module exposes a network-free, pure-standard-library toolkit:
Multinomial & Gaussian Naive Bayes, a Gini-impurity decision tree, K-means,
K-nearest-neighbours, PCA (power iteration), ROC/AUC, and a bootstrap p-value.

Source video IDs: O2L2Uv9pdDA, H3EjCKtlVog, _L39rN6gz7Y, 4b5d3muPQmA,
HVXime0nQeI, FgakZw6K1QQ, 4jRBRDbJemM, N4ZQQqyIf6k.

## Key API (facade methods)
bootstrap_pvalue, classify_knn, fit_decision_tree, health_check, initialize, kmeans, pca, roc_auc, set_event_bus, shutdown, train_naive_bayes

## Tests
```bash
python3 -m pytest modules/classical_ml/tests -q
```

## Import
```python
from enterprise.modules.classical_ml import create_classical_ml_module
m = create_classical_ml_module()
```
