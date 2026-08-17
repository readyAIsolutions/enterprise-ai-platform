"""ENI module plugin: guardrails (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "guardrails", "category": "Legacy Core", "version": "2.0.0",
        "purpose": "ENI Guardrails OS Module. Programmable input/output validators with a validate / fix / refix loop inspired by guardrails-ai, fully offline and stdlib-only. Two layers ship here: * **Classic layer**", "facades": ["facade", "get_event_bus", "get_registry", "guardrails", "health_check", "initialize", "list_guards", "list_validators", "register_guard", "register_validator", "registry", "set_event_bus", "shutdown", "validate"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "guardrails"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/guardrails/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
