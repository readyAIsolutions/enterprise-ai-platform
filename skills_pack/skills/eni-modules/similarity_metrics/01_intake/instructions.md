# Gather and normalize inputs

Purpose: similarity_metrics — cosine / Pearson / covariance similarity as a module.

## Role
Gather and normalize inputs for the `similarity_metrics` module.

## Inputs
Raw inputs/context for similarity_metrics: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for similarity_metrics. No unvalidated data passes.

## Scripts
python3 -m pytest modules/similarity_metrics/tests -q (validates core logic)
