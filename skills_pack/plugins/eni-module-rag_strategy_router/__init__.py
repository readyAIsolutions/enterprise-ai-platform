"""ENI module plugin: rag_strategy_router (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "rag_strategy_router", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "``rag_strategy_router`` — intent-based VECTOR / GRAPH / HYBRID RAG router. Grounded entirely in the real pulled transcript ``ColeMedin/p0FERNkpyHE.md`` ('Introducing RAG 2.0: Agentic RAG + Knowledge", "facades": ["dispatch", "health_check", "initialize", "register_retriever", "route", "route_batch", "set_event_bus", "shutdown", "strategies"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "rag_strategy_router"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/rag_strategy_router/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
