"""ENI module plugin: custom_agent_workflows (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "custom_agent_workflows", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "custom_agent_workflows — build your OWN AI coding workflows as a module. Grounded in the Cole Medin transcript *'The True Power of AI Coding — Build Your OWN Workflows (Full Guide)'* (https://www.you", "facades": ["build_initial_md", "execute", "health_check", "initialize", "plan", "primer", "research_codebase", "set_event_bus", "shutdown", "stats", "validate_code", "validate_plan"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "custom_agent_workflows"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/custom_agent_workflows/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
