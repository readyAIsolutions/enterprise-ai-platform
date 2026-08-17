"""ENI module plugin: second_brain (Knowledge Intake).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "second_brain", "category": "Knowledge Intake", "version": "1.0.0",
        "purpose": "Second Brain module — a knowledge capture & resurfacing engine. Grounded in three real pulled JE Van Clief transcripts: * 'Your Second Brain Is Not a Notes App' (-CUsfao6m7E) — a second brain", "facades": ["build_compounding_report", "capture", "health_check", "initialize", "link_ideas", "query_concept", "resurface", "shutdown"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "second_brain"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/second_brain/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
