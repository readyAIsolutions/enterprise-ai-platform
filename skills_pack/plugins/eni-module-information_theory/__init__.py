"""ENI module plugin: information_theory (Legacy Core).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "information_theory", "category": "Legacy Core", "version": "1.0.0",
        "purpose": "information_theory — Shannon entropy, mutual information, KL divergence, and a Wordle-style expected-information-gain solver, as an enterprise module. Grounded in real source transcripts: * StatQues", "facades": ["best_guess", "conditional_entropy", "entropy", "entropy_from_counts", "expected_information_gain", "health_check", "initialize", "joint_entropy", "kl_divergence", "mutual_information", "set_event_bus", "shutdown", "surprise", "wordle_feedback"]}


def _on_transform_tool_result(result, **_):
    try:
        tag = "information_theory"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/information_theory/tests -q")
            return {**result, "_eni_module": "\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
