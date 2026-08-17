"""ENI module plugin: claude_code_ui_harness (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "claude_code_ui_harness", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "Claude Code UI Harness — Enterprise Module wrapper. Grounded in the real pulled JE Van Clief transcript ``data/transcripts/JEVanClief/J2GLzkaUrBc.md`` — 'I'm Building a Custom Front End for Claude Co", "facades": ["audit_prd", "build_prd", "health_check", "initialize", "observe", "render_prd", "set_event_bus", "shutdown", "start_session", "track_usage", "usage_summary", "view"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "claude_code_ui_harness"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/claude_code_ui_harness/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
