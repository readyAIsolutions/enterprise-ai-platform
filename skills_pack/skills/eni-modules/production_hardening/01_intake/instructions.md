# Gather and normalize inputs

Purpose: Operational hardening checks for shipping an agent into production.

## Role
Gather and normalize inputs for the `production_hardening` module.

## Inputs
Raw inputs/context for production_hardening: deploy specs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for production_hardening. No unvalidated data passes.

## Scripts
python3 -m pytest modules/production_hardening/tests -q (validates core logic)
