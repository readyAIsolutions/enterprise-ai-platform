# Gather and normalize inputs

Purpose: ICM (Interpretable Context Methodology) — skill/prompt-engineering layer.

## Role
Gather and normalize inputs for the `icm` module.

## Inputs
Raw inputs/context for icm: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for icm. No unvalidated data passes.

## Scripts
python3 -m pytest modules/icm/tests -q (validates core logic)
