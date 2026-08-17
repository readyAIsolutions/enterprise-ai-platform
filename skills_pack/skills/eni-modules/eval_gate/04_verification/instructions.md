# Verify

Purpose: ENI Eval Gate OS Module — automated LLM evaluation gates (local & offline).

## Role
Verify for the `eval_gate` module.

## Inputs
The eval_gate deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/eval_gate/tests -q  (REAL suite; must pass)
