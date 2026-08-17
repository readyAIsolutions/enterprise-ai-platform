"""ENI module plugin: automation_triage (Build Quality).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "automation_triage", "category": "Build Quality", "version": "1.0.0",
        "purpose": "Automation Triage module — a decision framework for WHAT to automate. Implements the task-triage ladder, wrong-layer detection, 'what not to automate' guard, and one-client scoping guard extracted fr", "facades": ["detect_wrong_layer", "health_check", "initialize", "scope_for_one_client", "shutdown", "triage", "what_not_to_automate"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "automation_triage"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/automation_triage/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
