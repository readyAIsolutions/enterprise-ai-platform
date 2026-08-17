"""ENI module plugin: memory (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "memory", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "ENI Agent Memory OS Module. A mem0-style hybrid long-term memory engine: dependency-free semantic / episodic / declarative / procedural memory with per-user profiles, deterministic feature-hash embed", "facades": ["DEFAULT_DB", "add", "consolidate", "database_path", "delete", "forget", "get", "get_memories", "health_check", "initialize", "memory", "remember", "search", "search_all", "set_event_bus", "shutdown", "top_k", "update"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "memory"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/memory/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
