# Gather and normalize inputs

Purpose: Disaster Recovery OS Module

## Role
Gather and normalize inputs for the `disaster_recovery` module.

## Inputs
Raw inputs/context for disaster_recovery: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for disaster_recovery. No unvalidated data passes.

## Scripts
python3 -m pytest modules/disaster_recovery/tests -q (validates core logic)
