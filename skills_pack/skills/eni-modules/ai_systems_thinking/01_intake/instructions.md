# Gather and normalize inputs

Purpose: Feedback loops, coupling and systems lens for AI feature design.

## Role
Gather and normalize inputs for the `ai_systems_thinking` module.

## Inputs
Raw inputs/context for ai_systems_thinking: system designs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for ai_systems_thinking. No unvalidated data passes.

## Scripts
python3 -m pytest modules/ai_systems_thinking/tests -q (validates core logic)
