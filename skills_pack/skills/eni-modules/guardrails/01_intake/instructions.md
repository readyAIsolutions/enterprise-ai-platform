# Gather and normalize inputs

Purpose: ENI Guardrails OS Module.

## Role
Gather and normalize inputs for the `guardrails` module.

## Inputs
Raw inputs/context for guardrails: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for guardrails. No unvalidated data passes.

## Scripts
python3 -m pytest modules/guardrails/tests -q (validates core logic)
