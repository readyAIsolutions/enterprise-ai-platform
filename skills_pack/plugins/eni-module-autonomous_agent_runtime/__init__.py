"""ENI module plugin: autonomous_agent_runtime (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "autonomous_agent_runtime", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "ENI Autonomous Agent Runtime Module -- Multi-provider LLM abstraction. A first-class Platform Kernel module that wraps the ``provider_abstraction`` subsystem: a multi-provider LLM abstraction (provid", "facades": ["cost_summary", "facade", "fallback_status", "get_provider", "health_check", "health_check_all", "initialize", "list_providers", "register_providers_from_config", "reset_circuit", "set_event_bus", "shutdown"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "autonomous_agent_runtime"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/autonomous_agent_runtime/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
