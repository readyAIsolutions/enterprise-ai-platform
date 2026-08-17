# Gather and normalize inputs

Purpose: Layered memory model for agents (working/short/long) from AI-memory transcripts.

## Role
Gather and normalize inputs for the `ai_memory_hierarchy` module.

## Inputs
Raw inputs/context for ai_memory_hierarchy: agent memory. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for ai_memory_hierarchy. No unvalidated data passes.

## Scripts
python3 -m pytest modules/ai_memory_hierarchy/tests -q (validates core logic)
