"""ENI module plugin: ai_education_guardrails (Domain).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "ai_education_guardrails", "category": "Domain", "version": "1.0.0",
        "purpose": "AI Education Guardrails — responsible & effective AI use in academics/edtech. Distilled from four pulled JE Van Clief transcripts: * 'AI in Academics: How NOT to Use It' (czIBNYeiAuw) — learning h", "facades": ["assess_assignment", "assess_governance", "classify_usage", "detect", "engine", "health_check", "initialize", "shutdown"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "ai_education_guardrails"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/ai_education_guardrails/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
