# Gather and normalize inputs

Purpose: Probe/evaluate model reasoning attributes (psychometric-style evals).

## Role
Gather and normalize inputs for the `model_psychometrics` module.

## Inputs
Raw inputs/context for model_psychometrics: model responses. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for model_psychometrics. No unvalidated data passes.

## Scripts
python3 -m pytest modules/model_psychometrics/tests -q (validates core logic)
