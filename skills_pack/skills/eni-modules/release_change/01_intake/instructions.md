# Gather and normalize inputs

Purpose: Release & Change Management OS Module

## Role
Gather and normalize inputs for the `release_change` module.

## Inputs
Raw inputs/context for release_change: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for release_change. No unvalidated data passes.

## Scripts
python3 -m pytest modules/release_change/tests -q (validates core logic)
