# Gather and normalize inputs

Purpose: Task -> {read/skip/skills} routing table with token-budget guard.

## Role
Gather and normalize inputs for the `context_routing` module.

## Inputs
Raw inputs/context for context_routing: tasks. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for context_routing. No unvalidated data passes.

## Scripts
python3 -m pytest modules/context_routing/tests -q (validates core logic)
