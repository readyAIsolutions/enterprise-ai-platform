# Gather and normalize inputs

Purpose: Demo->production hardening linter across 8 scored dimensions + systems loops.

## Role
Gather and normalize inputs for the `production_agent_hardening` module.

## Inputs
Raw inputs/context for production_agent_hardening: agent specs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for production_agent_hardening. No unvalidated data passes.

## Scripts
python3 -m pytest modules/production_agent_hardening/tests -q (validates core logic)
