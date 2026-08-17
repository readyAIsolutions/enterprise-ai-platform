# Gather and normalize inputs

Purpose: ENI Model Security OS Module.

## Role
Gather and normalize inputs for the `model_security` module.

## Inputs
Raw inputs/context for model_security: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for model_security. No unvalidated data passes.

## Scripts
python3 -m pytest modules/model_security/tests -q (validates core logic)
