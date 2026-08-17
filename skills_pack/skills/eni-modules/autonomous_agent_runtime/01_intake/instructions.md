# Gather and normalize inputs

Purpose: ENI Autonomous Agent Runtime Module -- Multi-provider LLM abstraction.

## Role
Gather and normalize inputs for the `autonomous_agent_runtime` module.

## Inputs
Raw inputs/context for autonomous_agent_runtime: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for autonomous_agent_runtime. No unvalidated data passes.

## Scripts
python3 -m pytest modules/autonomous_agent_runtime/tests -q (validates core logic)
