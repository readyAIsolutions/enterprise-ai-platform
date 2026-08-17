# Gather and normalize inputs

Purpose: ENI TRIAD FORGE Module — White/Grey/Black Box security testing, as a kernel module.

## Role
Gather and normalize inputs for the `triadforge` module.

## Inputs
Raw inputs/context for triadforge: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for triadforge. No unvalidated data passes.

## Scripts
python3 -m pytest modules/triadforge/tests -q (validates core logic)
