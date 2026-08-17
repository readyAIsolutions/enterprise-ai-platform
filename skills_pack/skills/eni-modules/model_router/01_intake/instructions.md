# Gather and normalize inputs

Purpose: ENI Model Router OS Module — enterprise model-routing / fallback gateway.

## Role
Gather and normalize inputs for the `model_router` module.

## Inputs
Raw inputs/context for model_router: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for model_router. No unvalidated data passes.

## Scripts
python3 -m pytest modules/model_router/tests -q (validates core logic)
