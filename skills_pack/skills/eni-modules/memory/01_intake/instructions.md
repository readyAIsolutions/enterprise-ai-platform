# Gather and normalize inputs

Purpose: ENI Agent Memory OS Module.

## Role
Gather and normalize inputs for the `memory` module.

## Inputs
Raw inputs/context for memory: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for memory. No unvalidated data passes.

## Scripts
python3 -m pytest modules/memory/tests -q (validates core logic)
