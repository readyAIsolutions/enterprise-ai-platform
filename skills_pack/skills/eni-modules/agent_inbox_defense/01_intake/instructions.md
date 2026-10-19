# Gather and normalize inputs

Purpose: agent_inbox_defense — enterprise module wrapping a defensive scanner for

## Role
Gather and normalize inputs for the `agent_inbox_defense` module.

## Inputs
Raw inputs/context for agent_inbox_defense: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for agent_inbox_defense. No unvalidated data passes.

## Scripts
python3 -m pytest modules/agent_inbox_defense/tests -q (validates core logic)
