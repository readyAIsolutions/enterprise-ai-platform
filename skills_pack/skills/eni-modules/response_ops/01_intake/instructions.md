# Gather and normalize inputs

Purpose: ENI Response Ops Module — self-healing fleet supervisor + ICM routing hook.

## Role
Gather and normalize inputs for the `response_ops` module.

## Inputs
Raw inputs/context for response_ops: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for response_ops. No unvalidated data passes.

## Scripts
python3 -m pytest modules/response_ops/tests -q (validates core logic)
