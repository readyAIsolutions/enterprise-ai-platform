# ruff: noqa: T201
#!/usr/bin/env python3
"""ENI Enterprise — unified operational CLI (make it easy to use).

One command surface to inspect, boot, and drive the whole Enterprise Platform
from the terminal, instead of digging through Makefile / status.sh / server
entry points. FOSS + stdlib-only; all module calls are real Kernel operations.

Commands
--------
  eni status               -> one-line platform + service overview
  eni modules [--health]   -> list auto-discovered modules (+ health probe)
  eni up                   -> start the dashboard (:8421) in background
  eni dash                 -> open the dashboard in the default browser
  eni doctor               -> quick self-check (kernel import, discovery, health)
  eni agent-os <verb> [opts] -> drive the Agent OS module
       verbs: status | brief | oracle | draft | publish_latest | voice | hermes
  eni brief [--deliver file|signal|both]  -> run a morning brief now
  eni help
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent  # enterprise/
sys.path.insert(0, str(REPO))
os.chdir(REPO)

# Make the repo importable as `enterprise` (same trick pytest's root conftest uses).
try:
    import conftest  # noqa: F401
except Exception:
    pass


def _load_hermes_env() -> None:
    """Load SIGNAL_* and select env from ~/.hermes/.env so delivery works from
    any context (plain CLI, systemd, or the dashboard's subprocess) — not just
    when the Gateway has already sourced it."""
    env_file = Path.home() / ".hermes" / ".env"
    if not env_file.exists():
        return
    try:
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'").strip('"')
            if key.startswith("SIGNAL_") and not os.environ.get(key):
                os.environ[key] = val
    except Exception:
        pass


_load_hermes_env()

DASHBOARD_PORT = 8421
DASH_DIR = REPO / "dashboard"


# ── helpers ───────────────────────────────────────────────────────────────
def _enterprise_loaded() -> bool:
    try:
        import enterprise  # noqa: F401

        import conftest  # noqa: F401
        return True
    except Exception:
        return False


def _discover() -> list[str]:
    try:
        from enterprise.platform_kernel import ModuleRegistry

        return sorted(ModuleRegistry().discover())
    except Exception:
        return []


def _dashboard_running() -> bool:
    try:
        import urllib.request

        with urllib.request.urlopen(f"http://127.0.0.1:{DASHBOARD_PORT}/", timeout=2):
            return True
    except Exception:
        return False


def _start_dashboard() -> str:
    if _dashboard_running():
        return f"dashboard already running on :{DASHBOARD_PORT}"
    py = sys.executable
    # The repo's dashboard is a module server; try the canonical launcher first.
    candidates = [
        [py, str(DASH_DIR / "server.py")],
        [py, "-m", "uvicorn", "dashboard.server:app", "--port", str(DASHBOARD_PORT)],
    ]
    for c in candidates:
        try:
            subprocess.Popen(
                c, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(REPO)
            )
            time.sleep(2)
            if _dashboard_running():
                return f"dashboard started on :{DASHBOARD_PORT} ({c[0]} {c[1]})"
        except Exception:
            continue
    return f"dashboard may not have started; try: make run  (checked :{DASHBOARD_PORT})"


# ── module drivers ─────────────────────────────────────────────
def _agent_os() -> tuple:
    import asyncio

    from modules.agent_os import create_agent_os_module

    async def build() -> Any:
        m = create_agent_os_module({})
        await m.initialize()
        return m

    return asyncio.run(build())


def _brief(deliver: str = "file", limit: int = 5) -> None:
    import asyncio

    from modules.agent_os import create_agent_os_module

    async def run():
        m = create_agent_os_module({})
        await m.initialize()
        return m.run("morning_brief", limit=limit, deliver=deliver)

    res = asyncio.run(run())
    print(f"brief ok={res.get('ok')}  saved={res.get('saved')}")
    if "signal" in res:
        s = res["signal"]
        print(f"signal delivery ok={s.get('ok')} {s.get('error','')}")


def _agent_os_verb(verb: str, **kw: Any) -> None:  # noqa: ANN401
    m = _agent_os()
    print(json.dumps(m.run(verb, **kw), indent=2, default=str))


# ── command implementations ───────────────────────────────────────────────
def cmd_status() -> None:
    discovered = _discover()
    dash = _dashboard_running()
    print("ENI Enterprise Platform")
    print("-----------------------")
    print(f"modules auto-discovered : {len(discovered)}")
    print(f"agent_os present        : {'agent_os' in discovered}")
    print(f"dashboard (:{DASHBOARD_PORT})     : {'RUNNING' if dash else 'stopped'}")
    # services
    svc = [
        ("signal-cli-daemon", "signal-cli-daemon.service"),
        ("hermes-gateway", "hermes-gateway.service"),
        ("agent-os-brief", "agent-os-brief.timer"),
    ]
    for label, unit in svc:
        try:
            st = subprocess.run(
                ["systemctl", "--user", "is-active", unit],
                capture_output=True, text=True,
            ).stdout.strip()
            print(f"service {label:22}: {st or '?'}")
        except Exception:
            print(f"service {label:22}: n/a")


def cmd_modules(check_health: bool = False) -> None:
    discovered = _discover()
    if not discovered:
        print("no modules discoverable (is the kernel importable?)")
        return
    print(f"{len(discovered)} modules discovered:")
    if not check_health:
        for m in discovered:
            print(f"  - {m}")
        return
    import asyncio

    for name in discovered:
        try:
            mod = asyncio.run(_load_module(name))
            h = asyncio.run(mod.health_check())
            print(f"  - {name:32} {h.value}")
        except Exception as e:
            print(f"  - {name:32} error ({e})")


async def _load_module(name: str) -> Any:
    import importlib

    mod = importlib.import_module(f"modules.{name}")
    cls = getattr(mod, f"create_{name}_module", None)
    if cls is None:
        # fallback: find the @module registered class in the module
        for attr in vars(mod).values():
            if getattr(attr, "_meta_name", None) == name:
                cls = attr
                break
    if cls is None:
        err = "no factory"
        raise RuntimeError(err)
    inst = cls({})
    await inst.initialize()
    return inst


def cmd_doctor() -> None:
    import asyncio

    print("ENI Enterprise — doctor")
    print("  kernel importable :", _enterprise_loaded())
    discovered = _discover()
    print("  modules           :", len(discovered))
    print("  agent_os          :", "agent_os" in discovered)
    # health probe a few core modules
    for name in ["safety_governance", "hermes_controller", "agent_os"]:
        if name not in discovered:
            continue
        try:
            m = asyncio.run(_load_module(name))
            h = asyncio.run(m.health_check())
            print(f"  health {name:20}: {h.value}")
        except Exception as e:
            print(f"  health {name:20}: ERROR {e}")


def cmd_dash() -> None:
    if not _dashboard_running():
        print(_start_dashboard())
    opener = "xdg-open"  # linux
    subprocess.Popen([opener, f"http://127.0.0.1:{DASHBOARD_PORT}/"])
    print(f"opened dashboard at http://127.0.0.1:{DASHBOARD_PORT}/")


def cmd_up() -> None:
    print(_start_dashboard())
    # ensure brief timer is enabled
    try:
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", "agent-os-brief.timer"],
            capture_output=True, text=True,
        )
        print("agent-os-brief timer: enabled")
    except Exception:
        pass


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="eni", description="ENI Enterprise operational CLI"
    )
    ap.add_argument(
        "command", nargs="?", default="status",
        help="status|modules|up|dash|doctor|agent-os|brief|help",
    )
    ap.add_argument(
        "verb", nargs="?",
        help="agent-os verb: status|brief|oracle|draft|publish_latest|voice|hermes",
    )
    ap.add_argument("--health", action="store_true", help="modules: probe health")
    ap.add_argument("--deliver", default="file", help="brief: file|signal|both")
    ap.add_argument("--limit", type=int, default=5, help="brief/draft limit")
    ap.add_argument("--text", default="", help="agent-os voice text")

    args = ap.parse_args()
    cmd = args.command

    if cmd == "help":
        print(ap.format_help())
    elif cmd == "status":
        cmd_status()
    elif cmd == "modules":
        cmd_modules(check_health=args.health)
    elif cmd == "up":
        cmd_up()
    elif cmd == "dash":
        cmd_dash()
    elif cmd == "doctor":
        cmd_doctor()
    elif cmd == "brief":
        _brief(deliver=args.deliver, limit=args.limit)
    elif cmd == "agent-os":
        verb = args.verb or "status"
        if verb == "voice":
            _agent_os_verb("voice", text=args.text, auto=True)
        elif verb == "draft":
            _agent_os_verb("draft")
        elif verb == "publish_latest":
            _agent_os_verb("publish_latest", limit=args.limit)
        elif verb == "brief":
            _agent_os_verb("morning_brief", deliver=args.deliver, limit=args.limit)
        else:
            _agent_os_verb(verb)
    else:
        print(f"unknown command: {cmd}")
        print(ap.format_help())
        sys.exit(2)


if __name__ == "__main__":
    main()
