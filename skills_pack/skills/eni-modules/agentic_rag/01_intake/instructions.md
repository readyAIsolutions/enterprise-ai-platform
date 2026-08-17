# Gather and normalize inputs

Purpose: Agent-driven retrieval-augmented generation workflow.

## Role
Gather and normalize inputs for the `agentic_rag` module.

## Inputs
Raw inputs/context for agentic_rag: queries+corpus. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for agentic_rag. No unvalidated data passes.

## Scripts
python3 -m pytest modules/agentic_rag/tests -q (validates core logic)
