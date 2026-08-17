# Gather and normalize inputs

Purpose: Innovation R&D OS Module

## Role
Gather and normalize inputs for the `innovation_rd` module.

## Inputs
Raw inputs/context for innovation_rd: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for innovation_rd. No unvalidated data passes.

## Scripts
python3 -m pytest modules/innovation_rd/tests -q (validates core logic)
