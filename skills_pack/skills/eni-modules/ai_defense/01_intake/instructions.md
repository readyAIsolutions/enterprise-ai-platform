# Gather and normalize inputs

Purpose: ENI Enterprise AI Defense OS Module.

## Role
Gather and normalize inputs for the `ai_defense` module.

## Inputs
Raw inputs/context for ai_defense: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for ai_defense. No unvalidated data passes.

## Scripts
python3 -m pytest modules/ai_defense/tests -q (validates core logic)
