# Verify

Purpose: ENI Skill Factory Module — Meta-Skill Generator / Registry / Self-Evolution.

## Role
Verify for the `skill_factory` module.

## Inputs
The skill_factory deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/skill_factory/tests -q  (REAL suite; must pass)
