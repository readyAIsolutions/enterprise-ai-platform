"""ENI module plugin: artifact_pipeline (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "artifact_pipeline", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "Artifact Pipeline — navigate & organize all creative works (no LLM). Grounded in the JEVanClief transcript *'Watch Me Build Something Claude Code Can't Do Yet'* (https://www.youtube.com/watch?v=KC0VE", "facades": ["add", "advance", "all_renders", "browse", "derive", "group_by", "health", "health_check", "initialize", "pipeline", "readiness", "set_event_bus", "shutdown"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "artifact_pipeline"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/artifact_pipeline/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
