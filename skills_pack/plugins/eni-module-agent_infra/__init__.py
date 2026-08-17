"""ENI module plugin: agent_infra (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "agent_infra", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "Claude Code Superior — Infrastructure Module v1.0.0 ==================================================== Enterprise-grade infrastructure module re-implementing Claude Code's core systems as Python-na", "facades": ["buddy_manager", "component", "health_check", "infra", "initialize", "plugin_manager", "server", "set_event_bus", "shutdown", "tui", "voice"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "agent_infra"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/agent_infra/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
