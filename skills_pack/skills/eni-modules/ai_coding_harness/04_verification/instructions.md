# Verify

Purpose: Harness for coding-agent output: run, verify, audit.

## Role
Verify for the `ai_coding_harness` module.

## Inputs
The ai_coding_harness deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/ai_coding_harness/tests -q  (REAL suite; must pass)
