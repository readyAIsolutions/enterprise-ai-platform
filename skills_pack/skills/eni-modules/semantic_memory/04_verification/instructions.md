# Verify

Purpose: ENI Semantic Memory OS Module.

## Role
Verify for the `semantic_memory` module.

## Inputs
The semantic_memory deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/semantic_memory/tests -q  (REAL suite; must pass)
