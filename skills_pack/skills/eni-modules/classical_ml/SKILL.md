---
name: eni-module-classical_ml
description: Operate the ENI Enterprise `classical_ml` module (Legacy Core) — Classical-ML module — stdlib classical machine-learning toolkit. Use when working with classical_ml in the Enterprise Platform.
---

# Module skill: classical_ml

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: Classical-ML module — stdlib classical machine-learning toolkit.

## What it does
Classical-ML module — stdlib classical machine-learning toolkit.

Grounded in eight real StatQuest transcripts (see ``core`` for the per-algorithm
mapping). The module exposes a network-free, pure-standard-library toolkit:
Multinomial & Gaussian Naive Bayes, a Gini-impurity decision tree, K-means,
K-nearest-neighbours, PCA (power iteration), ROC/AUC, and a bootstrap p-value.

Source video IDs: O2L2Uv9pdDA, H3EjCKtlVog, _L39rN6gz7Y, 4b5d3muPQmA,
HVXime0nQeI, FgakZw6K1QQ, 4jRBRDbJemM, N4ZQQqyIf6k.

## Key API (facade methods on the @module class)
- bootstrap_pvalue\n- classify_knn\n- fit_decision_tree\n- health_check\n- initialize\n- kmeans\n- pca\n- roc_auc\n- set_event_bus\n- shutdown\n- train_naive_bayes

## Use
Import via:
```python
from enterprise.modules.classical_ml import create_classical_ml_module
m = create_classical_ml_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/classical_ml/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
