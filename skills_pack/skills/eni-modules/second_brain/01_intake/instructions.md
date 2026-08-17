# Gather and normalize inputs

Purpose: Knowledge capture/resurfacing engine: nodes+links, spaced repetition, concept query, compounding.

## Role
Gather and normalize inputs for the `second_brain` module.

## Inputs
Raw inputs/context for second_brain: knowledge notes. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for second_brain. No unvalidated data passes.

## Scripts
python3 -m pytest modules/second_brain/tests -q (validates core logic)
