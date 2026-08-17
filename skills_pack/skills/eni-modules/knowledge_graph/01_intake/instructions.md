# Gather and normalize inputs

Purpose: Knowledge Graph OS Module

## Role
Gather and normalize inputs for the `knowledge_graph` module.

## Inputs
Raw inputs/context for knowledge_graph: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for knowledge_graph. No unvalidated data passes.

## Scripts
python3 -m pytest modules/knowledge_graph/tests -q (validates core logic)
