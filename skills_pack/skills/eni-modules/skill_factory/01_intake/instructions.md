# Gather and normalize inputs

Purpose: ENI Skill Factory Module — Meta-Skill Generator / Registry / Self-Evolution.

## Role
Gather and normalize inputs for the `skill_factory` module.

## Inputs
Raw inputs/context for skill_factory: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for skill_factory. No unvalidated data passes.

## Scripts
python3 -m pytest modules/skill_factory/tests -q (validates core logic)
