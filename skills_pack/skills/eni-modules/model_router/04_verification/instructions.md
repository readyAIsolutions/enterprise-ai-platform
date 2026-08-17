# Verify

Purpose: ENI Model Router OS Module — enterprise model-routing / fallback gateway.

## Role
Verify for the `model_router` module.

## Inputs
The model_router deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/model_router/tests -q  (REAL suite; must pass)
