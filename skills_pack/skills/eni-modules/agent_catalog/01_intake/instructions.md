# Gather and normalize inputs

Purpose: ENI Agent Catalog Module -- unified specialist-agent registry.

## Role
Gather and normalize inputs for the `agent_catalog` module.

## Inputs
Raw inputs/context for agent_catalog: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for agent_catalog. No unvalidated data passes.

## Scripts
python3 -m pytest modules/agent_catalog/tests -q (validates core logic)
