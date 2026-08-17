# Verify

Purpose: Human review/approval gates inside agent runs.

## Role
Verify for the `human_in_the_loop` module.

## Inputs
The human_in_the_loop deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/human_in_the_loop/tests -q  (REAL suite; must pass)
