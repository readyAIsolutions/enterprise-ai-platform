"""ENI module plugin: codegen_audit (Build Quality).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "codegen_audit", "category": "Build Quality", "version": "1.0.0",
        "purpose": "codegen_audit — audit / evaluate AI-generated code. Grounded in three JE Van Clief coding-tool-eval transcripts: * ``_rtyhVD4v4A`` — 'One of These AI Coding Tools Failed Completely': comparing AI", "facades": ["analyze_dependencies", "audit", "evaluate_task", "health_check", "initialize", "review", "score", "set_event_bus", "shutdown"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "codegen_audit"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/codegen_audit/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
