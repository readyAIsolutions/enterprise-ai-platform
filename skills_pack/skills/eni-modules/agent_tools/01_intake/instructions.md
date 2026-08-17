# Gather and normalize inputs

Purpose: ENI Enterprise — Claude Code Tools Module v2.0.0

## Role
Gather and normalize inputs for the `agent_tools` module.

## Inputs
Raw inputs/context for agent_tools: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for agent_tools. No unvalidated data passes.

## Scripts
python3 -m pytest modules/agent_tools/tests -q (validates core logic)
