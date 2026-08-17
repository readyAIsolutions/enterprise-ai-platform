# Gather and normalize inputs

Purpose: voice_agent_hub — voice-driven orchestration of coding agents in a group call.

## Role
Gather and normalize inputs for the `voice_agent_hub` module.

## Inputs
Raw inputs/context for voice_agent_hub: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for voice_agent_hub. No unvalidated data passes.

## Scripts
python3 -m pytest modules/voice_agent_hub/tests -q (validates core logic)
