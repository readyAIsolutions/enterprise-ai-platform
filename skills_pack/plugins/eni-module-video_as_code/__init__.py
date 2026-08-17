"""ENI module plugin: video_as_code (Domain).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "video_as_code", "category": "Domain", "version": "1.0.0",
        "purpose": "Video as Code Enterprise Module. Grounded in the JEVanClief talk *'Video as Code: My AI Animation Stack'* (https://www.youtube.com/watch?v=yEa6dgh7wuc). Treats AI video/animation generation as softwa", "facades": ["event_bus", "health_check", "initialize", "run_pipeline", "runner", "set_event_bus", "shutdown"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "video_as_code"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/video_as_code/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
