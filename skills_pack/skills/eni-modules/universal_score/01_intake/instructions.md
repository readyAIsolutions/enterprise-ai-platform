# Gather and normalize inputs

Purpose: ENI Universal Build Score module.

## Role
Gather and normalize inputs for the `universal_score` module.

## Inputs
Raw inputs/context for universal_score: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for universal_score. No unvalidated data passes.

## Scripts
python3 -m pytest modules/universal_score/tests -q (validates core logic)
