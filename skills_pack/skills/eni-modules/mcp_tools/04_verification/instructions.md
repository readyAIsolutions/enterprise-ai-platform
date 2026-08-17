# Verify

Purpose: ENI MCP Tools Module — FastMCP-style tool registry & MCP serving layer.

## Role
Verify for the `mcp_tools` module.

## Inputs
The mcp_tools deliverable + its expectations.

## Definition of good output
All checks pass: the module's own test suite is green and the result meets the definition of good output.

## Scripts
python3 -m pytest modules/mcp_tools/tests -q  (REAL suite; must pass)
