# Gather and normalize inputs

Purpose: multiplayer_agent_triage — a Platform Kernel module for triaging problems and

## Role
Gather and normalize inputs for the `multiplayer_agent_triage` module.

## Inputs
Raw inputs/context for multiplayer_agent_triage: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for multiplayer_agent_triage. No unvalidated data passes.

## Scripts
python3 -m pytest modules/multiplayer_agent_triage/tests -q (validates core logic)
