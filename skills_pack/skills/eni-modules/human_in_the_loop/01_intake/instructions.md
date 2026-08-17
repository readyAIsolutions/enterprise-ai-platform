# Gather and normalize inputs

Purpose: Human review/approval gates inside agent runs.

## Role
Gather and normalize inputs for the `human_in_the_loop` module.

## Inputs
Raw inputs/context for human_in_the_loop: approval items. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for human_in_the_loop. No unvalidated data passes.

## Scripts
python3 -m pytest modules/human_in_the_loop/tests -q (validates core logic)
