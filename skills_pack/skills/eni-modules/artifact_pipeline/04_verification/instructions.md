# Verify

Purpose: Artifact Pipeline — navigate & organize all creative works (no LLM).

## Role
Verify for the `artifact_pipeline` module.

## Inputs
The artifact_pipeline deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/artifact_pipeline/tests -q  (REAL suite; must pass)
