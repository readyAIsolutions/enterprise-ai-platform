"""ENI module plugin: voice_agent_hub (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "voice_agent_hub", "category": "Legacy Core", "version": "0.0.0",
        "purpose": "voice_agent_hub — voice-driven orchestration of coding agents in a group call. Grounded in JEVanClief's 'We Ran Claude Code By Voice In A Group Call (The Future of Work?)' (https://www.youtube.com/wa", "facades": ["can_access_local_data", "dispatch", "grant_local_data_access", "health_check", "initialize", "interrupt", "parse_utterance", "revoke_local_data_access", "run_catalog_expansion", "run_frontend_review", "run_scale_review", "set_event_bus", "shutdown"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "voice_agent_hub"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/voice_agent_hub/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
