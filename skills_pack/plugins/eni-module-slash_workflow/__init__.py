"""ENI module plugin: slash_workflow (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "slash_workflow", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "slash_workflow — Plan->Implement->Validate AI-coding workflow with reusable markdown slash-commands, a plan-document schema, isolated-context sub-agents, a deterministic task cycle, and CLAUDE.md-styl", "facades": ["health_check", "initialize", "render_command", "run_workflow", "shutdown", "validate_plan"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "slash_workflow"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/slash_workflow/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
