"""ENI module plugin: a2a (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "a2a", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "ENI A2A Module -- Agent-to-Agent protocol (Google A2A style). A stdlib-only implementation of agent-to-agent messaging and task orchestration. Agents advertise themselves with an ``AgentCard`` (resol", "facades": ["create_task", "facade", "get_task", "handoff", "health_check", "initialize", "list_agents", "max_tasks", "persists", "register_agent_card", "router", "send_message", "set_event_bus", "shutdown", "store", "transition", "transport"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "a2a"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/a2a/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
