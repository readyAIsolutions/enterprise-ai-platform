# Gather and normalize inputs

Purpose: Structured tradeoff scoring for engineering decisions.

## Role
Gather and normalize inputs for the `engineering_tradeoff` module.

## Inputs
Raw inputs/context for engineering_tradeoff: options. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for engineering_tradeoff. No unvalidated data passes.

## Scripts
python3 -m pytest modules/engineering_tradeoff/tests -q (validates core logic)
