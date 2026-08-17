# Verify

Purpose: Research & Verification OS — Enterprise Platform Kernel Module v1.0.0

## Role
Verify for the `research_verification` module.

## Inputs
The research_verification deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/research_verification/tests -q  (REAL suite; must pass)
