# Verify

Purpose: Feedback loops, coupling and systems lens for AI feature design.

## Role
Verify for the `ai_systems_thinking` module.

## Inputs
The ai_systems_thinking deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/ai_systems_thinking/tests -q  (REAL suite; must pass)
