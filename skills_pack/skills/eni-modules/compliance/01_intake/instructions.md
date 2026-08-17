# Gather and normalize inputs

Purpose: ENI Enterprise Compliance OS Module.

## Role
Gather and normalize inputs for the `compliance` module.

## Inputs
Raw inputs/context for compliance: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for compliance. No unvalidated data passes.

## Scripts
python3 -m pytest modules/compliance/tests -q (validates core logic)
