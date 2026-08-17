"""ENI module plugin: procurement_bid_automation (Domain).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "procurement_bid_automation", "category": "Domain", "version": "1.0.0",
        "purpose": "Procurement Bid Automation module — deterministic government/RFP bid assistant. Grounded in the real JE Van Clief transcripts: * ``data/transcripts/JEVanClief/I-enT6szVQQ.md`` — 'I Used AI to Fix Go", "facades": ["analyze_solicitation", "assess_opportunity", "generate_capability_statement", "grade_profile", "health_check", "initialize", "recommend_codes", "set_event_bus", "shutdown"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "procurement_bid_automation"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/procurement_bid_automation/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
