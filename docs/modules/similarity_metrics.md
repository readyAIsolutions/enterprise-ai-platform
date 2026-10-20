# Module: `similarity_metrics`

- Category: Legacy Core · priority 69
- Version: 1.0.0
- Purpose: similarity_metrics — cosine / Pearson / covariance similarity as a module.
- Skill: `eni-module-similarity_metrics` (ICM stages) in skills_pack/skills/eni-modules/similarity_metrics/

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
initialize / health_check / shutdown lifecycle and a thin facade. It also
exposes a :func:`rank` facade for RAG retrieval ranking.

## Key API (facade methods)
cosine, covariance, dot, euclidean, health_check, initialize, magnitude, pearson, rank, set_event_bus, shutdown, std, variance

## Tests
```bash
python3 -m pytest modules/similarity_metrics/tests -q
```

## Import
```python
from enterprise.modules.similarity_metrics import create_similarity_metrics_module
m = create_similarity_metrics_module()
```
