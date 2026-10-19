# Verify

Purpose: ai_coding_workflow — a framework-agnostic, 3-phase AI-coding workflow

## Role
Verify for the `ai_coding_workflow` module.

## Inputs
The ai_coding_workflow deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/ai_coding_workflow/tests -q  (REAL suite; must pass)
