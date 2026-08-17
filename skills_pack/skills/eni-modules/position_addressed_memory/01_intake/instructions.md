# Gather and normalize inputs

Purpose: Position-addressed memory — *folder-as-memory* for AI context.

## Role
Gather and normalize inputs for the `position_addressed_memory` module.

## Inputs
Raw inputs/context for position_addressed_memory: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for position_addressed_memory. No unvalidated data passes.

## Scripts
python3 -m pytest modules/position_addressed_memory/tests -q (validates core logic)
