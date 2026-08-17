# Gather and normalize inputs

Purpose: ENI MCP Tools Module — FastMCP-style tool registry & MCP serving layer.

## Role
Gather and normalize inputs for the `mcp_tools` module.

## Inputs
Raw inputs/context for mcp_tools: inputs. Validate and stage them before any processing.

## Definition of good output
Normalised, staged inputs ready for mcp_tools. No unvalidated data passes.

## Scripts
python3 -m pytest modules/mcp_tools/tests -q (validates core logic)
