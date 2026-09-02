"""
ENI Enterprise Platform — Core package.
All enterprise modules are orchestrated by the Platform Kernel.
"""

__version__ = "1.0.0"
__author__ = "Eni Builder Enterprise"

from .platform_kernel import (
    PlatformOS,
    ModuleRegistry,
    EventBus,
    module,
    HealthStatus,
    LifecycleState,
)

__all__ = [
    "PlatformOS",
    "ModuleRegistry",
    "EventBus",
    "module",
    "HealthStatus",
    "LifecycleState",
]


# ─────────────────────────────────────────────────────────────────────────────
# Hermes drag-and-drop plugin surface.
#
# When this folder is dropped into ~/.hermes/plugins/ (or enabled as a project
# plugin), the Hermes plugin loader imports this package and calls register(ctx).
# We boot an in-process ModuleRegistry against OUR OWN modules/config so the
# enterprise self-sets-up inside Hermes. The /enterprise and /apply commands
# give in-chat status + initialize. Everything fails open: if the platform can t
# import or the registry can t boot, Hermes keeps running normally.
# ─────────────────────────────────────────────────────────────────────────────
if __package__:  # only define the plugin surface when imported as a real package
    import asyncio
    import os as _os
    import sys as _sys
    from pathlib import Path as _Path

    _ENTERPRISE_ROOT = _Path(__file__).resolve().parent

    _plugin_registry = None
    _plugin_err = ""

    def _plugin_locate() -> bool:
        global _plugin_registry, _plugin_err
        if _plugin_registry is not None:
            return True
        parent = str(_ENTERPRISE_ROOT.parent) or ""
        if not parent:
            _plugin_err = "cannot resolve enterprise parent"
            return False
        try:
            if parent not in _sys.path:
                _sys.path.insert(0, parent)
            from enterprise.platform_kernel import ModuleRegistry as _MR
            _plugin_registry = _MR  # cache the class
            return True
        except Exception as e:  # pragma: no cover - defensive
            _plugin_err = repr(e)
            return False

    def _plugin_load_cfg():
        try:
            import yaml as _y
            return _y.safe_load((_ENTERPRISE_ROOT / "config.yaml").read_text()) or {}
        except Exception:
            return {}

    _booted = None

    def _plugin_boot():
        global _booted
        if _booted is not None:
            return _booted
        try:
            if _plugin_locate():
                _booted = _plugin_registry(
                    _ENTERPRISE_ROOT / "modules", _plugin_load_cfg()
                )
                _booted.discover()
            else:
                _booted = None
        except Exception as e:  # pragma: no cover - defensive
            _plugin_err = repr(e)
            _booted = None
        return _booted

    def _plugin_status_md(_which: str = "build") -> str:
        reg = _plugin_boot()
        if reg is None:
            return f"Enterprise unavailable — {_plugin_err or 'platform import failed'}"
        try:
            recs = reg.list_modules()
            en = [r for r in recs if getattr(r, "enabled", False)]
            return (
                "# ENI Enterprise module status\n\n"
                f"{len(en)}/{len(recs)} enabled  ({len(recs)} discovered)\n"
            )
        except Exception as e:  # pragma: no cover - defensive
            return f"status failed: {e}"

    def _plugin_apply():
        reg = _plugin_boot()
        if reg is None:
            return f"apply failed — {_plugin_err or 'platform import failed'}"
        try:
            res = asyncio.run(reg.initialize_all())
            ok = sum(1 for v in res.values() if getattr(v, "name", "") == "HEALTHY")
            return f"initialized {ok}/{len(res)} modules" + (
                " (see /enterprise status)" if len(res) else ""
            )
        except Exception as e:  # pragma: no cover - defensive
            return f"apply failed: {e}"

    def _plugin_pre_llm(model: str = "", **_) -> object:
        reg = _plugin_boot()
        if reg is None:
            return None
        try:
            names = {
                r.name for r in reg.list_modules() if getattr(r, "enabled", False)
            }
            hits = []
            if {"rag", "kb_bridge", "agentic_rag"} & names:
                hits.append("KB/rag grounding available (rag, kb_bridge)")
            if "model_router" in names:
                hits.append("model_router active")
            if "eval_gate" in names:
                hits.append("eval_gate active")
            if "secret_broker" in names:
                hits.append("secret_broker active")
            if not hits:
                return None
            return {"context": " [ENI-enterprise] " + " ; ".join(hits)}
        except Exception:  # pragma: no cover - defensive
            return None

    def _plugin_session_end(**_):
        reg = _plugin_boot()
        if reg is None:
            return None
        try:
            names = {
                r.name for r in reg.list_modules() if getattr(r, "enabled", False)
            }
            if "skill_factory" in names or "task_harness" in names:
                return (
                    "[ENI-enterprise] skill_factory: if this session did a "
                    "reusable task, propose 1 new skill (curator)"
                )
        except Exception:  # pragma: no cover - defensive
            pass
        return None

    def _plugin_cmd_enterprise(raw: str) -> str:
        a = (raw or "").strip().lower()
        if a == "apply":
            return _plugin_apply()
        if a in ("status", "st", ""):
            return _plugin_status_md()
        return "usage: /enterprise status | apply | help"



_plugin_registry_gui = None

def _plugin_cmd_apply(raw: str) -> str:
    return _plugin_apply()

def _plugin_cmd_gui(raw: str) -> str:
    return _plugin_start_gui()

_gui_proc = None

def _plugin_start_gui():
    global _gui_proc
    try:
        if _gui_proc is not None and _gui_proc.poll() is None:
            return "GUI already running on http://127.0.0.1:8930"
        import subprocess as _sp
        _gui_proc = _sp.Popen([
            "python3",
            str(_ENTERPRISE_ROOT / "modules" / "telemetry" / "gui_server.py"),
            "8930",
        ])
        return "Started GUI on http://127.0.0.1:8930"
    except Exception as e:
        return "GUI start failed: " + repr(e)

_telemetry = None

def _plugin_telemetry():
    global _telemetry
    if _telemetry is None:
        try:
            from enterprise.modules.telemetry import telemetry as _t
            _telemetry = _t
        except Exception:
            _telemetry = False
    return _telemetry if _telemetry else None

def _plugin_reason_map():
    try:
        import json as _json
        p = _ENTERPRISE_ROOT / "modules" / "telemetry" / "module_purpose.json"
        return _json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        return {}

def _plugin_record(module, hook, tool, why):
    t = _plugin_telemetry()
    if t:
        try:
            t.record(module=module, hook=hook, tool=tool, why=why)
        except Exception:
            pass

def _plugin_on_start(session_id="", **k):
    t = _plugin_telemetry()
    if t:
        try:
            t.set_context(session_id=session_id)
        except Exception:
            pass

def _plugin_on_tool_hook(tool_name="", args=None, result=None, **k):
    reg = _plugin_boot()
    if reg is None:
        return None
    try:
        names = {r.name for r in reg.list_modules() if getattr(r, "enabled", False)}
        purpose = _plugin_reason_map()
        tool = str(tool_name or "")
        if not tool:
            return None
        gates = {
            "eval_gate": "post_tool_call",
            "codegen_audit": "transform_tool_result",
            "error_correction": "post_llm_call",
            "engineering_tradeoff": "post_llm_call",
            "research_verification": "pre_tool_call",
            "vuln_scanner": "post_tool_call",
        }
        for mod, hook in gates.items():
            if mod in names:
                w = purpose.get(mod, {}).get("why", "")
                _plugin_record(mod, hook, tool, w)
        if "model_router" in names:
            _plugin_record("model_router", "pre_llm_call", tool,
                           purpose.get("model_router", {}).get("why", ""))
        if "rag" in names or "agentic_rag" in names:
            _plugin_record("rag", "pre_llm_call", tool,
                           purpose.get("rag", {}).get("why", ""))
    except Exception:
        pass
    return None

def register(ctx) -> None:
    _plugin_boot()
    ctx.register_command("/enterprise", _plugin_cmd_enterprise,
                         "ENI enterprise in-process status/apply (drag-and-drop plugin)",
                         "status|apply|help")
    ctx.register_command("/apply", _plugin_cmd_apply,
                         "initialize all enabled enterprise modules", "")
    ctx.register_command("/gui", _plugin_cmd_gui,
                         "open the ENI build-module GUI (per-project module usage)", "")
    ctx.register_hook("pre_llm_call", _plugin_pre_llm)
    ctx.register_hook("on_session_start", _plugin_on_start)
    ctx.register_hook("post_tool_call", _plugin_on_tool_hook)
    ctx.register_hook("on_session_end", _plugin_session_end)
