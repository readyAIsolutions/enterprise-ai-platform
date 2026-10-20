"""ENI module plugin: similarity_metrics (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "similarity_metrics", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "similarity_metrics — cosine / Pearson / covariance similarity as a module. Grounded in three StatQuest transcripts (Josh Starmer): * *Cosine Similarity* (e9U0QAFbfLI) — dot product over the product", "facades": ["cosine", "covariance", "dot", "euclidean", "health_check", "initialize", "magnitude", "pearson", "rank", "set_event_bus", "shutdown", "std", "variance"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "similarity_metrics"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/similarity_metrics/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
