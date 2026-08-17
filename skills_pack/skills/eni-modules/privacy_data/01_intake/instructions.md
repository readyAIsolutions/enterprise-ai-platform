# Gather and normalize inputs

Purpose: Privacy & Data Governance OS Module

## Role
Gather and normalize inputs for the `privacy_data` module.

## Inputs
Raw inputs/context for privacy_data: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for privacy_data. No unvalidated data passes.

## Scripts
python3 -m pytest modules/privacy_data/tests -q (validates core logic)
