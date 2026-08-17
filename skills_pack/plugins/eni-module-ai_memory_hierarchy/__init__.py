"""ENI module plugin: ai_memory_hierarchy (Knowledge Intake).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "ai_memory_hierarchy", "category": "Knowledge Intake", "version": "1.0.0",
        "purpose": "AI Memory Hierarchy — an enterprise module modeling the AI memory hierarchy. Grounded in the JEVanClief transcript *'How a 1953 Word Game Explains AI Memory'* (https://www.youtube.com/watch?v=S3fXSc5", "facades": ["demote", "health", "health_check", "hierarchy", "initialize", "insert", "lock_weights", "promote", "retrieve", "set_event_bus", "set_prompt", "set_weights", "shutdown", "tier_summary"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "ai_memory_hierarchy"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/ai_memory_hierarchy/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
