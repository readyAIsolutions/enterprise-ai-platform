"""ENI module plugin: hybrid_kg_retrieval (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "hybrid_kg_retrieval", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "hybrid_kg_retrieval — an agentic RAG 2.0 retrieval engine that combines a vector/semantic index with an in-memory knowledge graph, routing each query to vector, graph, or BOTH strategies and fusing th", "facades": ["add_entity", "add_relation", "classify", "health_check", "index_document", "initialize", "retrieve", "set_event_bus", "shutdown"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "hybrid_kg_retrieval"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/hybrid_kg_retrieval/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
