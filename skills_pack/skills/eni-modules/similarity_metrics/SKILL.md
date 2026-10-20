---
name: eni-module-similarity_metrics
description: Operate the ENI Enterprise `similarity_metrics` module (Legacy Core) — similarity_metrics — cosine / Pearson / covariance similarity as a module. Use when working with similarity_metrics in the Enterprise Platform.
---

# Module skill: similarity_metrics

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: similarity_metrics — cosine / Pearson / covariance similarity as a module.

## What it does
similarity_metrics — cosine / Pearson / covariance similarity as a module.

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
initialize / health_check / shutdown lifecycle and a thin facade. It als

## Key API (facade methods on the @module class)
- cosine\n- covariance\n- dot\n- euclidean\n- health_check\n- initialize\n- magnitude\n- pearson\n- rank\n- set_event_bus\n- shutdown\n- std\n- variance

## Use
Import via:
```python
from enterprise.modules.similarity_metrics import create_similarity_metrics_module
m = create_similarity_metrics_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/similarity_metrics/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
