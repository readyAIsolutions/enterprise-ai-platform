# Verify

Purpose: Enterprise Prompt Guard OS Module — injection / jailbreak / policy guarding.

## Role
Verify for the `prompt_guard` module.

## Inputs
The prompt_guard deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/prompt_guard/tests -q  (REAL suite; must pass)
