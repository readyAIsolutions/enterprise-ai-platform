# Gather and normalize inputs

Purpose: ``rag_strategy_router`` — intent-based VECTOR / GRAPH / HYBRID RAG router.

## Role
Gather and normalize inputs for the `rag_strategy_router` module.

## Inputs
Raw inputs/context for rag_strategy_router: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for rag_strategy_router. No unvalidated data passes.

## Scripts
python3 -m pytest modules/rag_strategy_router/tests -q (validates core logic)
