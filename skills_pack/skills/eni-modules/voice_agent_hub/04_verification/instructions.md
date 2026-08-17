# Verify

Purpose: voice_agent_hub — voice-driven orchestration of coding agents in a group call.

## Role
Verify for the `voice_agent_hub` module.

## Inputs
The voice_agent_hub deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/voice_agent_hub/tests -q  (REAL suite; must pass)
