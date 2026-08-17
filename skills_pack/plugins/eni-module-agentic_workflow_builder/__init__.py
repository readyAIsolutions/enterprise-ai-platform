"""ENI module plugin: agentic_workflow_builder (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "agentic_workflow_builder", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "agentic_workflow_builder — compose agentic workflows (Claude Code + Cursor). Grounded in the JEVanClief transcript *'Claude Code + Cursor: Making Agentic workflows with an Agentic workflow!'* (https:", "facades": ["compose_workflow", "cost", "create_agent", "health_check", "initialize", "make_statement", "make_todo_list", "set_event_bus", "shutdown", "split_monolith", "stats"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "agentic_workflow_builder"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/agentic_workflow_builder/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
