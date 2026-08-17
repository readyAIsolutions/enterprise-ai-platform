# Gather and normalize inputs

Purpose: Production RAG System — Enterprise-grade Retrieval-Augmented Generation.

## Role
Gather and normalize inputs for the `rag` module.

## Inputs
Raw inputs/context for rag: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for rag. No unvalidated data passes.

## Scripts
python3 -m pytest modules/rag/tests -q (validates core logic)
