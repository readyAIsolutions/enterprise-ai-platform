"""ENI module plugin: swarm_bridge (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "swarm_bridge", "category": "Legacy Core", "version": "5.0.0",
        "purpose": "ENI Swarm Enterprise Module v5.0.0 =================================== Enterprise Platform Kernel module for the ENI Swarm — the 50-builder on-demand AI agent fleet coordinated by Master Driver v5.0.", "facades": []}


def _on_transform_tool_result(result, **_):
    try:
        tag = "swarm_bridge"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/swarm_bridge/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
