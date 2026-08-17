"""ENI module plugin: research_verification (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "research_verification", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "Research & Verification OS — Enterprise Platform Kernel Module v1.0.0 ====================================================================== Enterprise-grade module implementing the Research & Verifi", "facades": ["confidence", "detector", "execute_pipeline", "health_check", "initialize", "planner", "ranker", "shutdown", "synthesizer", "tracker"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "research_verification"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/research_verification/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
