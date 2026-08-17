# Verify

Purpose: Claude Code UI Harness — Enterprise Module wrapper.

## Role
Verify for the `claude_code_ui_harness` module.

## Inputs
The claude_code_ui_harness deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/claude_code_ui_harness/tests -q  (REAL suite; must pass)
