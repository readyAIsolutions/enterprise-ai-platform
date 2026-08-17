# Verify

Purpose: Probe/evaluate model reasoning attributes (psychometric-style evals).

## Role
Verify for the `model_psychometrics` module.

## Inputs
The model_psychometrics deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/model_psychometrics/tests -q  (REAL suite; must pass)
