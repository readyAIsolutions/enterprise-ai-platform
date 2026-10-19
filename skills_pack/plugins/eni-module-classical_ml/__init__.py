"""ENI module plugin: classical_ml (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "classical_ml", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "Classical-ML module — stdlib classical machine-learning toolkit. Grounded in eight real StatQuest transcripts (see ``core`` for the per-algorithm mapping). The module exposes a network-free, pure-sta", "facades": ["bootstrap_pvalue", "classify_knn", "fit_decision_tree", "health_check", "initialize", "kmeans", "pca", "roc_auc", "set_event_bus", "shutdown", "train_naive_bayes"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "classical_ml"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/classical_ml/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
