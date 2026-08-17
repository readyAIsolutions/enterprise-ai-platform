# Gather and normalize inputs

Purpose: Claude Code Core — Enterprise Platform Kernel Module v2.0.0

## Role
Gather and normalize inputs for the `agent_core` module.

## Inputs
Raw inputs/context for agent_core: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for agent_core. No unvalidated data passes.

## Scripts
python3 -m pytest modules/agent_core/tests -q (validates core logic)
