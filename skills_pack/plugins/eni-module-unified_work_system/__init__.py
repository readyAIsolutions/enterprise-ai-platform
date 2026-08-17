"""ENI module plugin: unified_work_system (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "unified_work_system", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "ENI Unified Work System Module Enterprise-grade module that runs creative, technical/software, and business work as ONE system — grounded in the JEVanClief one-system thesis. At the heart of the mod", "facades": ["check_consistency", "health_check", "initialize", "render", "set_event_bus", "shutdown", "store_memory", "work_system"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "unified_work_system"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/unified_work_system/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
