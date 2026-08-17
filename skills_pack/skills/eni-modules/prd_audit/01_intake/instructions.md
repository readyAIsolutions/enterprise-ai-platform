# Gather and normalize inputs

Purpose: prd_audit — PRD-gated build workflow: write the PRD, audit it with a second

## Role
Gather and normalize inputs for the `prd_audit` module.

## Inputs
Raw inputs/context for prd_audit: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for prd_audit. No unvalidated data passes.

## Scripts
python3 -m pytest modules/prd_audit/tests -q (validates core logic)
