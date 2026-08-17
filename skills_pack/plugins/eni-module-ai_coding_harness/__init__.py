"""ENI module plugin: ai_coding_harness (Agent Workflow).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "ai_coding_harness", "category": "Agent Workflow", "version": "1.0.0",
        "purpose": "AI Coding Harness module — repeatable agentic Claude-Code coding workflows. Implements the prompt->scaffold->generate->iterate->verify loop that JE Van Clief demonstrates across four transcripts (web", "facades": ["build_context", "generate_from_prompt", "health_check", "initialize", "scaffold", "shutdown"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "ai_coding_harness"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/ai_coding_harness/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
