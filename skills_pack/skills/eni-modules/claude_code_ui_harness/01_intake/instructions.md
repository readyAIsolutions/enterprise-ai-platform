# Gather and normalize inputs

Purpose: Claude Code UI Harness — Enterprise Module wrapper.

## Role
Gather and normalize inputs for the `claude_code_ui_harness` module.

## Inputs
Raw inputs/context for claude_code_ui_harness: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for claude_code_ui_harness. No unvalidated data passes.

## Scripts
python3 -m pytest modules/claude_code_ui_harness/tests -q (validates core logic)
