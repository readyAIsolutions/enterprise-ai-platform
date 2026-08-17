# Gather and normalize inputs

Purpose: ENI A2A Module -- Agent-to-Agent protocol (Google A2A style).

## Role
Gather and normalize inputs for the `a2a` module.

## Inputs
Raw inputs/context for a2a: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for a2a. No unvalidated data passes.

## Scripts
python3 -m pytest modules/a2a/tests -q (validates core logic)
