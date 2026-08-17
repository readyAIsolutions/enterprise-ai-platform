# Verify

Purpose: Multi-participant AI+human group chat: round-robin, moderator focus, escalation, handoffs.

## Role
Verify for the `group_chat_orchestration` module.

## Inputs
The group_chat_orchestration deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/group_chat_orchestration/tests -q  (REAL suite; must pass)
