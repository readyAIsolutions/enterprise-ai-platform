"""ENI module plugin: human_in_the_loop (Agent Workflow).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "human_in_the_loop", "category": "Agent Workflow", "version": "1.0.0",
        "purpose": "Human-in-the-Loop module — a human-oversight orchestration layer for the compute layer. Grounded in the real pulled JE Van Clief transcript 'Afternoon tea: Why Humans Belong in the Compute Layer' (30", "facades": ["audit_log", "health_check", "initialize", "pending_escalations", "queue_stats", "resolve_action", "route_action", "shutdown"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "human_in_the_loop"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/human_in_the_loop/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
