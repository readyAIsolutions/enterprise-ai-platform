# Gather and normalize inputs

Purpose: ENI Agent Graph Module — langgraph-style stateful agent graph orchestration.

## Role
Gather and normalize inputs for the `agent_graph` module.

## Inputs
Raw inputs/context for agent_graph: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for agent_graph. No unvalidated data passes.

## Scripts
python3 -m pytest modules/agent_graph/tests -q (validates core logic)
