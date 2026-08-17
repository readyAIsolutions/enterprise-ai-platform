# Gather and normalize inputs

Purpose: Multi-participant AI+human group chat: round-robin, moderator focus, escalation, handoffs.

## Role
Gather and normalize inputs for the `group_chat_orchestration` module.

## Inputs
Raw inputs/context for group_chat_orchestration: chat turns. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for group_chat_orchestration. No unvalidated data passes.

## Scripts
python3 -m pytest modules/group_chat_orchestration/tests -q (validates core logic)
