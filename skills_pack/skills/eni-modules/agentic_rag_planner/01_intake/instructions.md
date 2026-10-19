# Gather and normalize inputs

Purpose: Agentic RAG retrieval-strategy planner module.

## Role
Gather and normalize inputs for the `agentic_rag_planner` module.

## Inputs
Raw inputs/context for agentic_rag_planner: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for agentic_rag_planner. No unvalidated data passes.

## Scripts
python3 -m pytest modules/agentic_rag_planner/tests -q (validates core logic)
