"""ENI module plugin: folder_agency_system (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "folder_agency_system", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "folder_agency_system — a folder/org-structure system that organizes an AI startup's work as an on-disk folder hierarchy of capabilities, projects, and agents, with immutable version-one templates, dep", "facades": ["create_agent", "create_atlas", "create_capability", "create_project", "create_workbench", "health_check", "import_template", "initialize", "librarian_query", "manifest", "read_atlas", "render_tree", "set_event_bus", "shutdown"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "folder_agency_system"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/folder_agency_system/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
