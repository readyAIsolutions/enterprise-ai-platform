# Gather and normalize inputs

Purpose: ENI Knowledge Base OS Module

## Role
Gather and normalize inputs for the `kb_bridge` module.

## Inputs
Raw inputs/context for kb_bridge: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for kb_bridge. No unvalidated data passes.

## Scripts
python3 -m pytest modules/kb_bridge/tests -q (validates core logic)
