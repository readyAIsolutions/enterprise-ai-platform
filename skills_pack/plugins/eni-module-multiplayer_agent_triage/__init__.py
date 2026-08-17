"""ENI module plugin: multiplayer_agent_triage (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "multiplayer_agent_triage", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "multiplayer_agent_triage — a Platform Kernel module for triaging problems and wins when many AI agents / players operate together in one shared product. Grounded in the JEVanClief transcript *'Alpha", "facades": ["critical_items", "engine", "health_check", "initialize", "record_win", "set_event_bus", "shutdown", "summary", "token_spend", "triage"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "multiplayer_agent_triage"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/multiplayer_agent_triage/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
