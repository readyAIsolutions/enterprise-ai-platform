"""ENI module plugin: paper_feeds (Knowledge Intake).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "paper_feeds", "category": "Knowledge Intake", "version": "2.0.0",
        "purpose": "Paper-feeds module — daily AI research digests (arXiv/HF/PwC/AlphaXiv). Rebuilt v2.0: structured ``Paper`` model, primary arXiv Atom API ingestion with HTML fallback, change detection (only *new* pap", "facades": ["health_check", "initialize", "pull_one", "pull_today", "seen_count", "shutdown"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "paper_feeds"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/paper_feeds/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
