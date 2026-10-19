"""ENI module plugin: composable_workflow_engine (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "composable_workflow_engine", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "composable_workflow_engine — a compose-your-own context-engineering workflow engine for the ENI Enterprise Platform. Grounded ENTIRELY in ColeMedin's 'The True Power of AI Coding - Build Your OWN Wor", "facades": ["all_templates", "compose", "describe", "get_template", "health_check", "initialize", "register_template", "run", "set_event_bus", "shutdown", "validate_template"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "composable_workflow_engine"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/composable_workflow_engine/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
