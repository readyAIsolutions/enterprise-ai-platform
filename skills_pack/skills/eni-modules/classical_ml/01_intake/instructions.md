# Gather and normalize inputs

Purpose: Classical-ML module — stdlib classical machine-learning toolkit.

## Role
Gather and normalize inputs for the `classical_ml` module.

## Inputs
Raw inputs/context for classical_ml: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for classical_ml. No unvalidated data passes.

## Scripts
python3 -m pytest modules/classical_ml/tests -q (validates core logic)
