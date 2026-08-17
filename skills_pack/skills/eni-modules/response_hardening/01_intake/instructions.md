# Gather and normalize inputs

Purpose: ENI Response Hardening module.

## Role
Gather and normalize inputs for the `response_hardening` module.

## Inputs
Raw inputs/context for response_hardening: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for response_hardening. No unvalidated data passes.

## Scripts
python3 -m pytest modules/response_hardening/tests -q (validates core logic)
