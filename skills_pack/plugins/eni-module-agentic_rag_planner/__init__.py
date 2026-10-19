"""ENI module plugin: agentic_rag_planner (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "agentic_rag_planner", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "Agentic RAG retrieval-strategy planner module. Grounded in Cole Medin's 'Introducing RAG 2.0: Agentic RAG + Knowledge Graphs' (YouTube p0FERNkpyHE). The agent is given BOTH a vector/semantic-search t", "facades": ["health_check", "initialize", "plan", "plan_multi", "set_event_bus", "shutdown"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "agentic_rag_planner"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/agentic_rag_planner/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
