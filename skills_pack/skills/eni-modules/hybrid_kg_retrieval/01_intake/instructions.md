# Gather and normalize inputs

Purpose: hybrid_kg_retrieval — an agentic RAG 2.0 retrieval engine that combines a

## Role
Gather and normalize inputs for the `hybrid_kg_retrieval` module.

## Inputs
Raw inputs/context for hybrid_kg_retrieval: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for hybrid_kg_retrieval. No unvalidated data passes.

## Scripts
python3 -m pytest modules/hybrid_kg_retrieval/tests -q (validates core logic)
