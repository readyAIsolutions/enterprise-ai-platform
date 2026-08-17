# Verify

Purpose: Guardrails for using AI in education (anti-cheating, learning-first).

## Role
Verify for the `ai_education_guardrails` module.

## Inputs
The ai_education_guardrails deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/ai_education_guardrails/tests -q  (REAL suite; must pass)
