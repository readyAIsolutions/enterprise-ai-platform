"""ENI module plugin: triadforge (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "triadforge", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "ENI TRIAD FORGE Module — White/Grey/Black Box security testing, as a kernel module. Wraps the standalone TRIAD FORGE hacker box (~/Desktop/TriadForge) into the ENI Enterprise Platform so it boots HEA", "facades": ["add_adversary_target", "add_source_target", "add_web_target", "export_sarif", "fix_snippet", "health_check", "initialize", "list_findings", "run_scan", "scan_llm", "scan_source", "scan_web", "set_event_bus", "shutdown"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "triadforge"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/triadforge/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
