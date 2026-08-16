#!/usr/bin/env python3
"""
ENI Swarm CLI — Unified Command-Line Interface
===============================================
Entry point for the `eni-swarm` command.

Provides subcommands to control every ENI component:
  start, stop, status, heartbeat, launch, config, task,
  logs, dashboard, daemon, sync, compress, glyph, evolve,
  skill-forge, version

Run:  eni-swarm <command> [options]
"""

from __future__ import annotations

import os
import sys
import time
import json
import subprocess
import signal
import threading
import socket
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

# ─── Path setup ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]  # .../ENI_Swarm_NEW
LIB_DIR = ROOT / "lib"
sys.path.insert(0, str(LIB_DIR))

# ─── ANSI color codes ───────────────────────────────────────────────────────
class C:
    RST   = "\033[0m"
    BOLD  = "\033[1m"
    DIM   = "\033[2m"
    RED   = "\033[31m"
    GRN   = "\033[32m"
    YEL   = "\033[33m"
    BLU   = "\033[34m"
    MAG   = "\033[35m"
    CYN   = "\033[36m"
    WHT   = "\033[37m"

def color(text: str, code: str) -> str:
    return f"{code}{text}{C.RST}"

def banner():
    print(f"""
{C.CYN}{C.BOLD}  ███████╗███╗   ██╗██╗    ███████╗██╗    ██╗ █████╗ ██████╗ ███╗   ███╗{C.RST}
{C.CYN}{C.BOLD}  ██╔════╝████╗  ██║██║    ██╔════╝██║    ██║██╔══██╗██╔══██╗████╗ ████║{C.RST}
{C.CYN}{C.BOLD}  █████╗  ██╔██╗ ██║██║    ███████╗██║ █╗ ██║███████║██████╔╝██╔████╔██║{C.RST}
{C.CYN}{C.BOLD}  ██╔══╝  ██║╚██╗██║██║    ╚════██║██║███╗██║██╔══██║██╔══██╗██║╚██╔╝██║{C.RST}
{C.CYN}{C.BOLD}  ███████╗██║ ╚████║██║    ███████║╚███╔███╔╝██║  ██║██║  ██║██║ ╚═╝ ██║{C.RST}
{C.CYN}{C.BOLD}  ╚══════╝╚═╝  ╚═══╝╚═╝    ╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝{C.RST}
{C.MAG}  v4.0.0  —  Unified Swarm Coordination Interface{C.RST}
""")


def ok(msg: str, *args):
    s = msg.format(*args) if args else msg
    print(f" {C.GRN}{C.BOLD}✔{C.RST} {s}")

def warn(msg: str, *args):
    s = msg.format(*args) if args else msg
    print(f" {C.YEL}{C.BOLD}⚠{C.RST} {s}")

def err(msg: str, *args):
    s = msg.format(*args) if args else msg
    print(f" {C.RED}{C.BOLD}✘{C.RST} {s}")

def info(msg: str, *args):
    s = msg.format(*args) if args else msg
    print(f" {C.BLU}{C.BOLD}→{C.RST} {s}")

def title(msg: str):
    print(f"\n{C.BOLD}{C.WHT}{msg}{C.RST}")
    print(f"{C.DIM}{'─' * 60}{C.RST}")


# ─── Helpers ────────────────────────────────────────────────────────────────

def _swarm_pid_file() -> Path:
    return Path.home() / ".cache" / "eni_swarm" / "master_driver.pid"

def _is_daemon_running(port: int = 8765) -> bool:
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
        s.close()
        return True
    except Exception:
        return False

def _start_daemon() -> subprocess.Popen:
    from kb.daemon.eni_kb_daemon import run_daemon as kb_run
    proc = subprocess.Popen(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0,'" + str(LIB_DIR) + "'); "
         "from kb.daemon.eni_kb_daemon import run_daemon; run_daemon()"],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc

def _stop_daemon():
    try:
        import requests
        requests.post("http://127.0.0.1:8765/shutdown", timeout=2)
    except Exception:
        # Fallback: kill by process search
        subprocess.run(["pkill", "-f", "eni_kb_daemon"], capture_output=True)


# ─── Subcommand implementations ─────────────────────────────────────────────

def cmd_start(project: Optional[str] = None, workers: int = 0):
    """Start the ENI swarm for a project."""
    banner()
    title("Starting ENI Swarm")

    try:
        from eni.master_driver import main_loop
    except ImportError as e:
        err("Cannot import master_driver: {}", e)
        sys.exit(1)

    if project:
        os.environ["ENI_PROJECT"] = project
        info("Project: {}", project)

    pid_file = _swarm_pid_file()
    if pid_file.exists():
        try:
            old_pid = int(pid_file.read_text().strip())
            os.kill(old_pid, 0)
            warn("Master driver already running (PID: {})", old_pid)
            info("Use 'eni-swarm stop' to stop it first, or 'status' to check")
            return
        except (OSError, ValueError):
            pid_file.unlink(missing_ok=True)

    info("Launching master driver...")
    info("Workers: {} (auto-detected from task roster)", workers or "auto")

    # Run in foreground by default; background with &
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))

    try:
        main_loop()
    except KeyboardInterrupt:
        ok("Swarm stopped gracefully")
    finally:
        pid_file.unlink(missing_ok=True)


def cmd_stop(project: Optional[str] = None):
    """Stop swarm workers gracefully."""
    title("Stopping ENI Swarm")

    # Try daemon HTTP first
    try:
        import requests
        r = requests.get("http://127.0.0.1:8765/stop", timeout=2)
        ok("Daemon stop signal sent: {}", r.status_code)
    except Exception:
        pass

    # Kill master driver
    pid_file = _swarm_pid_file()
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            pid_file.unlink()
            ok("Master driver (PID {}) terminated", pid)
        except OSError:
            info("No running master driver found")

    # Kill any remaining agent_term processes
    try:
        subprocess.run(["pkill", "-f", "eni_agent_term.py"], capture_output=True)
        ok("Mini agent terminals terminated")
    except Exception:
        pass

    # Kill compression workers
    try:
        subprocess.run(["pkill", "-f", "eni_compression_pipeline"], capture_output=True)
        ok("Compression workers terminated")
    except Exception:
        pass

    ok("Swarm stopped")


def cmd_status():
    """Show full swarm status."""
    banner()
    title("ENI Swarm Status")

    # Check master driver
    pid_file = _swarm_pid_file()
    master_alive = False
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            master_alive = True
            ok("Master Driver: RUNNING (PID: {})", pid)
        except (OSError, ValueError):
            warn("Master Driver: STOPPED")
    else:
        warn("Master Driver: NOT STARTED (no PID file)")

    # Check daemon
    if _is_daemon_running(8765):
        ok("KB Daemon: RUNNING (port 8765)")
    else:
        warn("KB Daemon: STOPPED")

    # Check sync server
    if _is_daemon_running(8766):
        ok("Sync Server: LISTENING (port 8766)")
    else:
        warn("Sync Server: NOT LISTENING")

    # Read master status
    status_file = ROOT / "tasks" / "status" / "MASTER_STATUS.md"
    if status_file.exists():
        print(f"\n{C.BOLD}--- MASTER_STATUS.md ---{C.RST}")
        print(status_file.read_text()[:2000])
    else:
        warn("No MASTER_STATUS.md found")

    # State file
    state_file = Path.home() / ".cache" / "eni_swarm" / "master_state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            cycle = state.get("cycle", 0)
            minis = state.get("minis", {})
            print(f"\n{C.BOLD}--- Swarm State (cycle {cycle}) ---{C.RST}")
            for name, m in minis.items():
                alive = "✅" if m.get("alive") else "❌"
                pid = m.get("pid", "?")
                cycles = m.get("cycles", 0)
                print(f"  {alive} {C.CYN}{name}{C.RST}  pid={pid}  silent_cycles={cycles}")
        except Exception:
            pass

    # Config check
    cfg_dir = ROOT / "config"
    for cfg_file in ["eni_build_tasks.json", "eni_herself_tasks.json"]:
        p = cfg_dir / cfg_file
        if p.exists():
            ok("Config: {} ({:,} bytes)", cfg_file, p.stat().st_size)
        else:
            warn("Config: {} MISSING", cfg_file)


def cmd_heartbeat():
    """Show real-time pulse monitor."""
    banner()
    title("ENI Swarm Heartbeat Monitor")
    info("Polling every 3s — press Ctrl+C to stop")
    print()

    state_file = Path.home() / ".cache" / "eni_swarm" / "master_state.json"
    status_dir = ROOT / "tasks" / "status"

    def fmt_age(ts: float) -> str:
        if not ts:
            return "never"
        age = time.time() - ts
        if age < 60:
            return f"{age:.0f}s"
        elif age < 3600:
            return f"{age/60:.1f}m"
        return f"{age/3600:.1f}h"

    try:
        last_state = {}
        while True:
            # Clear screen (mostly)
            print(f"\033[2J\033[H{C.CYN}{C.BOLD}ENI SWARM — HEARTBEAT{C.RST}  {datetime.now().strftime('%H:%M:%S')}")
            print(f"{C.DIM}{'═' * 60}{C.RST}")

            # Daemon health
            daemon = "🟢" if _is_daemon_running(8765) else "🔴"
            sync = "🟢" if _is_daemon_running(8766) else "🔴"
            master_alive = False
            pid_file = _swarm_pid_file()
            if pid_file.exists():
                try:
                    os.kill(int(pid_file.read_text().strip()), 0)
                    master_alive = True
                except Exception:
                    pass
            master = "🟢" if master_alive else "🔴"

            print(f"  Daemon: {daemon}  |  Sync: {sync}  |  Master: {master}")
            print(f"  {C.DIM}http://127.0.0.1:8765/health   │   http://127.0.0.1:8766 (sync)   │   coordination loop{C.RST}")
            print()

            # Minis
            if state_file.exists():
                try:
                    state = json.loads(state_file.read_text())
                    cycle = state.get("cycle", 0)
                    minis = state.get("minis", {})

                    print(f"  {C.BOLD}Cycle: {cycle}{C.RST}  |  Minis: {len(minis)}")
                    print(f"  {C.DIM}{'─' * 60}{C.RST}")

                    # Show each mini with pulse
                    for name, m in sorted(minis.items()):
                        alive = m.get("alive", False)
                        cycles = m.get("cycles", 0)
                        mtime = m.get("mtime", 0)
                        age = fmt_age(mtime)

                        # Pulse visual
                        if not alive:
                            pulse = f"{C.RED}█ DEAD{C.RST}"
                        elif cycles == 0:
                            pulse = f"{C.GRN}█ LIVE{C.RST}"
                        elif cycles <= 3:
                            pulse = f"{C.GRN}▌ healthy{C.RST}"
                        elif cycles <= 6:
                            pulse = f"{C.YEL}▌ quiet{C.RST}"
                        else:
                            pulse = f"{C.RED}▌ silent{C.RST}"

                        # Check status file content
                        status_text = ""
                        sf = status_dir / f"STATUS_{name}.md"
                        if sf.exists():
                            try:
                                st = sf.read_text().splitlines()
                                if st:
                                    first_line = st[0].strip()
                                    if first_line.startswith("[") and "]" in first_line:
                                        status_text = first_line[:40]
                            except Exception:
                                pass

                        line = f"  {pulse}  {C.CYN}{name:25s}{C.RST}  {age:>6s} ago  |  {status_text}"
                        print(line)

                    if not minis:
                        print(f"  {C.DIM}(no minis loaded — start the swarm with 'eni-swarm start'){C.RST}")

                except Exception:
                    print(f"  {C.DIM}(reading state file...){C.RST}")
            else:
                print(f"  {C.DIM}(no state file — swarm not yet started){C.RST}")

            print(f"\n{C.DIM}{'═' * 60}{C.RST}")
            print(f"{C.DIM}  ENI Swarm v4.0.0  —  Ctrl+C to exit pulse{C.RST}")
            time.sleep(3)

    except KeyboardInterrupt:
        print(f"\n{C.GRN}Heartbeat monitor stopped.{C.RST}")


def cmd_launch():
    """Launch visible terminal windows for builder minis."""
    title("Launching ENI Builder Terminals")

    builder_script = ROOT / "launchers" / "eni_launch_builders.sh"
    if builder_script.exists():
        info("Running: {}", builder_script)
        subprocess.run(["bash", str(builder_script)])
    else:
        # Fallback: try to detect and launch
        info("No launcher script found, launching directly...")
        terminals = ["gnome-terminal", "konsole", "xfce4-terminal", "xterm", "alacritty", "kitty"]
        term = None
        for t in terminals:
            if shutil.which(t):
                term = t
                break

        if not term:
            err("No terminal emulator found (tried: {})", ", ".join(terminals))
            sys.exit(1)

        info("Using terminal: {}", term)

        # Launch compression pipeline in a terminal
        pipeline = LIB_DIR / "compression" / "eni_compression_pipeline.py"
        if term in ("gnome-terminal", "alacritty", "kitty"):
            subprocess.Popen([term, "--", sys.executable, str(pipeline)])
        elif term in ("konsole",):
            subprocess.Popen([term, "-e", sys.executable, str(pipeline)])
        elif term in ("xfce4-terminal",):
            subprocess.Popen([term, "--command", sys.executable + " " + str(pipeline)])
        else:
            subprocess.Popen([term, "-e", sys.executable, str(pipeline)])

        ok("Builder terminal launched")


def cmd_config(action: str = "show"):
    """Show or edit swarm config."""
    cfg_dir = ROOT / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)

    if action == "show":
        title("ENI Swarm Configuration")
        for f in sorted(cfg_dir.iterdir()):
            if f.suffix in (".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"):
                size = f.stat().st_size
                print(f"\n{C.BOLD}{C.CYN}{f.name}{C.RST} ({size:,} bytes)")
                print(f"{C.DIM}{'─' * 50}{C.RST}")
                try:
                    if f.suffix == ".json":
                        data = json.loads(f.read_text())
                        # Show summary: keys and task count
                        if "tasks" in data:
                            print(f"  Tasks: {len(data['tasks'])}")
                            for t in data["tasks"][:10]:
                                print(f"    - {t.get('name', '?')}: {t.get('title', '')[:60]}")
                            if len(data["tasks"]) > 10:
                                print(f"    ... and {len(data['tasks']) - 10} more")
                        else:
                            print(f"  Keys: {', '.join(sorted(data.keys()))}")
                    else:
                        print(f.read_text()[:500])
                except Exception as e:
                    warn("Could not read: {}", e)

    elif action == "edit":
        editor = os.environ.get("EDITOR", "vim")
        cfg_files = sorted(cfg_dir.glob("*.json"))
        if cfg_files:
            info("Opening config directory in {}: {}", editor, cfg_dir)
            subprocess.call([editor, str(cfg_dir)])
        else:
            warn("No config files found in {}", cfg_dir)

    else:
        err("Unknown config action: {} (use 'show' or 'edit')", action)
        sys.exit(1)


def cmd_task(action: str = "list", name: Optional[str] = None, **kwargs):
    """Manage task roster."""
    cfg_dir = ROOT / "config"

    if action == "list":
        title("ENI Swarm Task Roster")
        for task_file in ["eni_build_tasks.json", "eni_herself_tasks.json"]:
            p = cfg_dir / task_file
            if p.exists():
                print(f"\n{C.BOLD}{task_file}{C.RST}")
                try:
                    data = json.loads(p.read_text())
                    tasks = data.get("tasks", [])
                    for t in tasks:
                        print(f"  {C.CYN}{t.get('name'):20s}{C.RST}  {t.get('title', '')[:55]}")
                        print(f"    workdir: {t.get('workdir', '~')}   model: {t.get('model', 'default')}")
                except Exception as e:
                    err("Failed to read {}: {}", task_file, e)
            else:
                warn("{} not found", task_file)

    elif action == "add":
        if not name:
            err("Usage: eni-swarm task add --name <name> --title <title> --workdir <dir> --task <task>")
            sys.exit(1)
        task_file = cfg_dir / "eni_build_tasks.json"
        data = json.loads(task_file.read_text()) if task_file.exists() else {"tasks": []}
        new_task = {
            "name": kwargs.get("name", name),
            "title": kwargs.get("title", name),
            "workdir": kwargs.get("workdir", os.path.expanduser("~")),
            "model": kwargs.get("model", "tencent/hy3:free"),
            "task": kwargs.get("task", ""),
        }
        data["tasks"].append(new_task)
        task_file.write_text(json.dumps(data, indent=2))
        ok("Added task: {}", new_task["name"])

    elif action == "remove":
        if not name:
            err("Usage: eni-swarm task remove --name <name>")
            sys.exit(1)
        for task_file in [cfg_dir / "eni_build_tasks.json", cfg_dir / "eni_herself_tasks.json"]:
            if task_file.exists():
                data = json.loads(task_file.read_text())
                original = len(data.get("tasks", []))
                data["tasks"] = [t for t in data.get("tasks", []) if t.get("name") != name]
                if len(data["tasks"]) < original:
                    task_file.write_text(json.dumps(data, indent=2))
                    ok("Removed '{}' from {}", name, task_file.name)
                    return
        warn("Task '{}' not found", name)

    else:
        err("Unknown task action: {} (use 'list', 'add', or 'remove')", action)
        sys.exit(1)


def cmd_logs(follow: bool = False, mini: Optional[str] = None):
    """View swarm logs."""
    log_file = Path.home() / ".cache" / "eni_swarm" / "coordination.log"

    if mini:
        # Show status file for a specific mini
        status_file = ROOT / "tasks" / "status" / f"STATUS_{mini}.md"
        if status_file.exists():
            print(f"{C.BOLD}=== STATUS_{mini}.md ==={C.RST}")
            print(status_file.read_text())
        else:
            warn("No status file for mini: {}", mini)
        return

    if follow:
        info("Following logs (Ctrl+C to stop)...")
        try:
            # Tail -f style
            if log_file.exists():
                subprocess.run(["tail", "-f", str(log_file)])
            else:
                warn("Log file not found, waiting...")
                while True:
                    time.sleep(1)
        except KeyboardInterrupt:
            ok("Log following stopped")
    else:
        if log_file.exists():
            # Show last 50 lines
            lines = log_file.read_text().splitlines()
            for line in lines[-50:]:
                print(line)
        else:
            warn("No logs yet — start the swarm first")

    # Also show KB daemon log
    kb_log = Path.home() / ".eni" / "kb" / "logs" / "eni_kb_daemon.log"
    if kb_log.exists():
        print(f"\n{C.DIM}--- KB Daemon log (last 20 lines) ---{C.RST}")
        for line in kb_log.read_text().splitlines()[-20:]:
            print(f"  {C.DIM}{line}{C.RST}")


def cmd_dashboard():
    """Start web dashboard on port 8420."""
    title("ENI Swarm Dashboard")

    port = 8420
    import http.server
    import socketserver

    class DashboardHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/" or self.path == "/index.html":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(self._render_dashboard().encode())
            elif self.path == "/api/status":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(self._gather_status()).encode())
            elif self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "dashboard": "eni-swarm"}).encode())
            else:
                super().do_GET()

        @staticmethod
        def _gather_status() -> dict:
            state_file = Path.home() / ".cache" / "eni_swarm" / "master_state.json"
            status = {
                "daemon": _is_daemon_running(8765),
                "sync": _is_daemon_running(8766),
                "timestamp": time.time(),
                "minis": {},
            }
            if state_file.exists():
                try:
                    state = json.loads(state_file.read_text())
                    status["cycle"] = state.get("cycle", 0)
                    for name, m in state.get("minis", {}).items():
                        status["minis"][name] = {
                            "alive": m.get("alive", False),
                            "cycles_silent": m.get("cycles", 0),
                            "pid": m.get("pid", 0),
                        }
                except Exception:
                    pass
            return status

        @staticmethod
        def _render_dashboard() -> str:
            status = DashboardHandler._gather_status()
            # Build a simple HTML dashboard
            minis_html = ""
            for name, m in sorted(status.get("minis", {}).items()):
                alive = "🟢" if m.get("alive") else "🔴"
                minis_html += f"""
                <tr>
                    <td>{alive}</td>
                    <td>{name}</td>
                    <td>{m.get('cycles_silent', 0)}</td>
                    <td>{m.get('pid', '?')}</td>
                </tr>"""

            return f"""<!DOCTYPE html>
<html>
<head>
    <title>ENI Swarm Dashboard</title>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="5">
    <style>
        body {{ font-family: 'Fira Code', 'Courier New', monospace; background: #0a0a0f; color: #c0c0d0; margin: 0; padding: 20px; }}
        h1 {{ color: #00c8ff; }}
        .card {{ background: #12121a; border: 1px solid #2a2a3a; border-radius: 8px; padding: 15px; margin: 10px 0; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ text-align: left; color: #888; padding: 8px; border-bottom: 1px solid #2a2a3a; }}
        td {{ padding: 8px; border-bottom: 1px solid #1a1a2a; }}
        .status {{ font-size: 1.2em; padding: 10px; border-radius: 4px; }}
        .green {{ color: #00ff88; }}
        .red {{ color: #ff4455; }}
        .yellow {{ color: #ffaa00; }}
    </style>
</head>
<body>
    <h1>⚡ ENI Swarm Dashboard</h1>

    <div class="card">
        <h3>Services</h3>
        <table>
            <tr><th>Service</th><th>Status</th><th>Port</th></tr>
            <tr>
                <td>KB Daemon</td>
                <td class="{('green' if status.get('daemon') else 'red')}">{('● RUNNING' if status.get('daemon') else '○ STOPPED')}</td>
                <td>8765</td>
            </tr>
            <tr>
                <td>Sync Server</td>
                <td class="{('green' if status.get('sync') else 'yellow')}">{('● LISTENING' if status.get('sync') else '○ STOPPED')}</td>
                <td>8766</td>
            </tr>
        </table>
    </div>

    <div class="card">
        <h3>Swarm Minis — Cycle {status.get('cycle', 0)}</h3>
        <table>
            <tr><th></th><th>Mini</th><th>Silent Cycles</th><th>PID</th></tr>
            {minis_html}
        </table>
        {('<p class="yellow">No minis loaded — start with <code>eni-swarm start</code></p>' if not status.get('minis') else '')}
    </div>

    <div class="card">
        <small>Dashboard on port 8420  ·  Auto-refresh 5s  ·  <a href="/api/status" style="color:#00c8ff">/api/status</a></small>
    </div>
</body>
</html>"""

    info("Starting dashboard on http://127.0.0.1:{}", port)
    info("Open your browser or use: curl http://127.0.0.1:{}/api/status", port)
    info("Press Ctrl+C to stop")

    try:
        with socketserver.TCPServer(("0.0.0.0", port), DashboardHandler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        ok("Dashboard stopped")


def cmd_daemon(action: str = "status"):
    """Manage the ENI Knowledge Base Daemon."""
    title(f"ENI KB Daemon — {action}")

    if action == "start":
        if _is_daemon_running(8765):
            warn("Daemon already running on port 8765")
        else:
            proc = _start_daemon()
            time.sleep(1)
            if _is_daemon_running(8765):
                ok("Daemon started (PID: {})", proc.pid)
                info("Health: http://127.0.0.1:8765/health")
            else:
                warn("Daemon may still be starting... check logs")

    elif action == "stop":
        _stop_daemon()
        time.sleep(1)
        if not _is_daemon_running(8765):
            ok("Daemon stopped")
        else:
            # Force kill
            subprocess.run(["pkill", "-9", "-f", "eni_kb_daemon"], capture_output=True)
            ok("Daemon force-stopped")

    elif action == "restart":
        _stop_daemon()
        time.sleep(1)
        proc = _start_daemon()
        time.sleep(1)
        ok("Daemon restarted (PID: {})", proc.pid)

    elif action == "status":
        if _is_daemon_running(8765):
            ok("Daemon: RUNNING")
            info("Health: http://127.0.0.1:8765/health")
            info("Status: http://127.0.0.1:8765/status")
            try:
                import requests
                r = requests.get("http://127.0.0.1:8765/status", timeout=2)
                data = r.json()
                for svc, s in data.get("services", {}).items():
                    status_icon = "🟢" if s.get("running") else "🔴"
                    print(f"  {status_icon} {svc}: pid={s.get('pid', '?')}")
            except Exception:
                warn("Could not fetch detailed status")
        else:
            warn("Daemon: STOPPED")
            info("Start with: eni-swarm daemon start")

    else:
        err("Unknown daemon action: {} (use start|stop|restart|status)", action)
        sys.exit(1)


def cmd_sync(action: str = "status"):
    """Manage ENI peer sync."""
    title(f"ENI Sync — {action}")

    if action == "once":
        info("Running one sync cycle...")
        try:
            from kb.sync.sync_daemon import load_state, load_peers, sync_with_peer, scan_sync_dirs, save_state, SyncState, FileEntry, time as _time
            state = load_state()
            current = scan_sync_dirs()
            for fname, entry in current.items():
                if fname not in state.files or state.files[fname].hash != entry.hash:
                    entry.version = state.files.get(fname, FileEntry("", 0, 0, "", 0)).version + 1
                    state.files[fname] = entry
            save_state(state)

            peers = load_peers()
            for p in peers:
                ok_count = sync_with_peer(p, state)
                if ok_count:
                    ok("Synced with: {}", p.get("name", p.get("host")))
                else:
                    warn("Failed to sync with: {}", p.get("name", p.get("host")))
            ok("Sync cycle complete")
        except Exception as e:
            err("Sync failed: {}", e)
            sys.exit(1)

    elif action == "daemon":
        info("Starting sync daemon (client + server)...")
        try:
            from kb.sync.sync_daemon import sync_loop, run_sync_server, log, logging
            # Start sync server in a thread, client loop in foreground
            threading.Thread(target=run_sync_server, daemon=True).start()
            sync_loop()
        except KeyboardInterrupt:
            ok("Sync daemon stopped")
        except Exception as e:
            err("Sync daemon failed: {}", e)
            sys.exit(1)

    elif action == "peers":
        info("Current peer configuration:")
        try:
            from kb.sync.sync_daemon import load_peers
            peers = load_peers()
            for p in peers:
                enabled = "✅" if p.get("enabled", True) else "❌"
                print(f"  {enabled} {p.get('name', '?'):15s}  {p.get('host', '?')}:{p.get('port', 8766)}")
        except Exception as e:
            err("Could not load peers: {}", e)

    elif action == "status":
        if _is_daemon_running(8766):
            ok("Sync Server: LISTENING on port 8766")
        else:
            warn("Sync Server: NOT LISTENING")

        # Show state
        try:
            from kb.sync.sync_daemon import load_state
            state = load_state()
            print(f"  Tracked files: {len(state.files)}")
            print(f"  Known peers: {len(state.peer_versions)}")
            if state.last_sync:
                ago = time.time() - state.last_sync
                print(f"  Last sync: {ago:.0f}s ago")
            else:
                print(f"  Last sync: never")
        except Exception as e:
            warn("Could not load sync state: {}", e)

    else:
        err("Unknown sync action: {} (use once|daemon|peers|status)", action)
        sys.exit(1)


def cmd_compress(file: Optional[str] = None):
    """Compress a file through the ENI pipeline."""
    if not file:
        err("Usage: eni-swarm compress <FILE>")
        sys.exit(1)

    fpath = Path(file).expanduser().resolve()
    if not fpath.exists():
        err("File not found: {}", fpath)
        sys.exit(1)

    title(f"ENI Compression Pipeline — {fpath.name}")

    try:
        from compression.eni_compression_pipeline import compress_markdown, WENYAN, paq8_compress, pxpipe_encode, compress_with_glyphs
    except ImportError as e:
        err("Cannot import compression pipeline: {}. Install deps first.", e)
        sys.exit(1)

    content = fpath.read_text()
    original_size = len(content)

    info("Original size: {:,} bytes", original_size)

    # Wenyan encode
    info("Step 1: Wenyan encoding...")
    wenyan = WENYAN.encode(content)
    info("  Wenyan output: {} chars (from {:,})", len(wenyan), original_size)

    # PAQ8 compress
    info("Step 2: PAQ8 compression...")
    try:
        compressed = paq8_compress(content.encode())
        ratio = original_size / len(compressed) if compressed else 0
        ok("  PAQ8: {:,} → {:,} bytes ({:.1f}x)", original_size, len(compressed), ratio)
    except Exception as e:
        warn("  PAQ8 failed, using zlib fallback: {}", e)
        import zlib
        compressed = zlib.compress(content.encode(), 9)
        ratio = original_size / len(compressed) if compressed else 0

    # PXPipe PNG
    info("Step 3: PXPipe PNG steganography...")
    try:
        from compression.eni_compression_pipeline import CARRIERS_DIR
        carrier = CARRIERS_DIR / f"eni_compress_{fpath.stem}.png"
        pxpipe_encode(compressed, carrier)
        ok("  Carrier: {} ({:,} bytes)", carrier.name, carrier.stat().st_size)
    except Exception as e:
        warn("  PXPipe failed: {} (dependencies may be missing)", e)
        carrier = None

    # Glyph compression
    info("Step 4: Glyph token compression...")
    glyph_compressed = compress_with_glyphs(wenyan)
    glyph_savings = (len(wenyan) - len(glyph_compressed)) / max(1, len(wenyan)) * 100
    ok("  Glyph: {} → {} chars ({:.1f}% savings)", len(wenyan), len(glyph_compressed), glyph_savings)

    # Summary
    print(f"\n{C.BOLD}--- Compression Summary ---{C.RST}")
    print(f"  Pipeline:   Wenyan → PAQ8 → PXPipe → Glyphs")
    print(f"  Original:   {original_size:,} bytes")
    print(f"  Compressed: {len(compressed):,} bytes (PAQ8)")
    print(f"  Ratio:      {ratio:.2f}x")
    if carrier:
        print(f"  Carrier:    {carrier}")
    print(f"  Glyph:      {len(glyph_compressed):,} token-chars")


def cmd_glyph(action: str = "list", **kwargs):
    """Manage ENI glyphs."""
    title(f"ENI Glyph Management — {action}")

    try:
        from kb.glyphs.glyph_allocator import GlyphAllocator, initialize_defaults
    except ImportError as e:
        err("Cannot import glyph allocator: {}", e)
        sys.exit(1)

    allocator = GlyphAllocator()

    if action == "list":
        category = kwargs.get("category")
        glyphs = allocator.list_glyphs(category)
        if glyphs:
            print(f"  {len(glyphs)} glyphs registered:")
            for g in glyphs:
                token_display = repr(g.token) if g.token else "?"
                print(f"  {C.CYN}{g.name:25s}{C.RST}  [{g.category}] freq={g.frequency}  len={len(g.expansion)}  token={token_display}")
        else:
            info("No glyphs registered. Run 'eni-swarm glyph allocate' to create some.")

    elif action == "allocate":
        name = kwargs.get("name")
        expansion = kwargs.get("expansion")
        category = kwargs.get("category", "custom")
        if not name or not expansion:
            err("Usage: eni-swarm glyph allocate --name <name> --expansion <text> [--category <cat>]")
            sys.exit(1)
        g = allocator.allocate(name, expansion, category)
        ok("Allocated glyph: {} ({})", g.name, g.category)

    elif action == "expand":
        text = kwargs.get("text", "")
        if not text:
            err("Usage: eni-swarm glyph expand --text '<text with glyph tokens>'")
            sys.exit(1)
        result = allocator.expand(text)
        print(result)

    elif action == "compress":
        text = kwargs.get("text", "")
        if not text:
            err("Usage: eni-swarm glyph compress --text '<text to compress>'")
            sys.exit(1)
        result = allocator.compress(text)
        print(result)

    elif action == "stats":
        s = allocator.stats()
        print(f"  Total glyphs:        {s['total_glyphs']}")
        print(f"  Total uses:          {s['total_uses']:,}")
        print(f"  Avg savings/use:     {s['avg_savings_per_use']:.1f} chars")
        print(f"  By category:")
        for cat, count in sorted(s.get("by_category", {}).items()):
            print(f"    {cat}: {count}")

    elif action == "init":
        allocator = initialize_defaults()
        ok("Initialized {} default glyphs", len(allocator.glyphs))

    else:
        err("Unknown glyph action: {} (use list|allocate|expand|compress|stats|init)", action)
        sys.exit(1)


def cmd_evolve(generations: int = 50):
    """Run compression evolution."""
    banner()
    title(f"ENI Compression Evolution — {generations} generations")

    try:
        from kb.evolution.adaptive_compression import EvolutionEngine
    except ImportError as e:
        err("Cannot import evolution engine: {}", e)
        sys.exit(1)

    info("Initializing genetic algorithm population...")
    engine = EvolutionEngine(pop_size=20)
    engine.run(generations)

    best = engine.population[0] if engine.population else None
    if best:
        ok("Evolution complete!")
        print(f"\n{C.BOLD}Best Genome:{C.RST}")
        print(f"  Fitness:     {best.fitness:.4f}")
        print(f"  PAQ8 Level:  {best.paq8_level}")
        print(f"  LSB Bits:    {best.pxpipe_lsb_bits}")
        print(f"  Wenyan Dens: {best.wenyan_density:.3f}")
        print(f"  Glyph Thresh:{best.glyph_threshold:.3f}")
        print(f"  Generation:  {best.generation}")


def cmd_skill_forge(workers: int = 4):
    """Run the skill forge swarm."""
    banner()
    title(f"ENI Skill Forge Swarm — {workers} workers")

    try:
        from kb.workers.skill_forge_swarm import SkillForgeSwarm, SPEC_DIR
    except ImportError as e:
        err("Cannot import skill forge: {}", e)
        sys.exit(1)

    swarm = SkillForgeSwarm(num_workers=workers)
    swarm.load_specs()

    if not swarm.specs:
        warn("No skill specs found!")
        info("Creating default specs...")

        from kb.workers.skill_forge_swarm import DEFAULT_SPECS, asdict
        for spec in DEFAULT_SPECS:
            spec_file = SPEC_DIR / f"{spec.name}.json"
            spec_file.write_text(json.dumps(asdict(spec), indent=2))
            info("  Created: {}", spec_file.name)

        swarm.load_specs()

    info("Building {} skills with {} workers...", len(swarm.specs), workers)
    results = swarm.run()

    # Summary
    ok_count = sum(1 for r in results if r.success)
    print(f"\n{C.BOLD}--- Forge Results ---{C.RST}")
    print(f"  Total:  {len(results)}")
    print(f"  Passed: {ok_count} {C.GRN}✅{C.RST}")
    print(f"  Failed: {len(results) - ok_count}")
    print(f"  Rate:   {ok_count/len(results)*100:.1f}%" if results else "")


def cmd_version():
    """Show ENI Swarm version."""
    from eni import __version__
    print(f"{C.CYN}{C.BOLD}ENI Swarm v{__version__}{C.RST}")
    print(f"  Root:      {ROOT}")
    print(f"  Library:   {LIB_DIR}")
    print(f"  Python:    {sys.version}")
    print(f"  Exec:      {sys.executable}")

    # Check optional deps
    deps = {
        "click": False, "pillow": False, "numpy": False, "mcp": False,
        "pygls": False, "requests": False, "psutil": False, "mistune": False,
    }
    for dep in deps:
        try:
            __import__(dep)
            deps[dep] = True
        except ImportError:
            pass

    print(f"\n{C.BOLD}Optional Dependencies:{C.RST}")
    for dep, available in deps.items():
        icon = f"{C.GRN}✔{C.RST}" if available else f"{C.DIM}✘{C.RST}"
        print(f"  {icon} {dep}")


# ─── CLI dispatch ───────────────────────────────────────────────────────────

def cmd_tui():
    """Launch the live TUI dashboard."""
    try:
        from eni.tui_dashboard import EniTuiDashboard
        dashboard = EniTuiDashboard()
        dashboard.run()
    except ImportError as e:
        err("TUI dashboard requires 'rich': {}", e)
        info("Install with: pip install rich")


def cmd_model(action: str = "list", model_name: Optional[str] = None, code: int = 500):
    """Manage model auto-fallback."""
    from eni.model_resolver import ModelResolver
    resolver = ModelResolver()

    if action == "list":
        models = resolver.get_all()
        print(f"\\n{C.BOLD}Model Registry{C.RST}")
        print(f"{C.DIM}{'='*90}{C.RST}")
        print(f"  {'Model':<45} {'Alive':<8} {'Cooldown':<12} {'Fails':<8} {'Uses':<8}")
        print(f"  {C.DIM}{'-'*85}{C.RST}")
        for m in models:
            alive = f"{C.GRN}🟢{C.RST}" if m["alive"] else f"{C.RED}🔴{C.RST}"
            cd = f"{m['cooldown_remaining']}s" if m["in_cooldown"] else "—"
            print(f"  {m['name']:<45} {alive:<8} {cd:<12} {m['consecutive_fails']:<8} {m['total_uses']:<8}")
        print(f"\n  Healthy: {resolver.healthy_count()}/{len(models)}")
    elif action == "resolve":
        result = resolver.resolve(model_name)
        ok(f"Resolved: {result or 'NO MODELS AVAILABLE'}")
    elif action == "fail":
        if not model_name:
            err("--model-name required for fail")
            return
        resolver.mark_failed(model_name, code)
        ok(f"Marked {model_name} as failed (HTTP {code})")
    elif action == "success":
        if not model_name:
            err("--model-name required for success")
            return
        resolver.mark_success(model_name)
        ok(f"Marked {model_name} as successful")
    elif action == "add":
        if not model_name:
            err("--model-name required for add")
            return
        resolver.add_model(model_name)
        ok(f"Added: {model_name}")
    elif action == "reset":
        resolver.reset_all()
        ok("All models reset to healthy")


def cmd_snapshot(action: str = "list", name: Optional[str] = None,
                 snapshot_id: Optional[str] = None, keep: int = 10):
    """Manage swarm snapshots."""
    from eni.snapshot import SnapshotManager
    mgr = SnapshotManager()

    if action == "create":
        sid = mgr.create(name)
        ok(f"Snapshot created: {sid}")
        snap = mgr.get_snapshot(sid)
        if snap:
            s = snap.get("summary", {})
            info("Files: {} ({} status, {} tasks)", s.get("total_files", 0),
                 s.get("status_files", 0), s.get("task_files", 0))
    elif action == "list":
        snapshots = mgr.list_snapshots()
        if not snapshots:
            warn("No snapshots found")
            return
        for s in snapshots[:10]:
            created = s.get("created_at", "")[:19]
            files = s.get("summary", {}).get("total_files", 0)
            minis = len(s.get("minis", {}))
            sid = s["snapshot_id"]
            print(f"  {C.CYN}{sid:<30}{C.RST} {created}  {files} files  {minis} minis")
    elif action == "restore":
        if not snapshot_id:
            err("--id required for restore")
            return
        report = mgr.restore(snapshot_id)
        if "error" in report:
            err(report["error"])
        else:
            ok("Restored {} files", len(report["restored"]))
    elif action == "delete":
        if not snapshot_id:
            err("--id required for delete")
            return
        ok = mgr.delete(snapshot_id)
        info("{}", "Deleted" if ok else "Not found")
    elif action == "prune":
        deleted = mgr.prune(keep=keep)
        ok(f"Pruned {deleted} snapshots (keeping {keep})")
    elif action == "auto":
        sid = mgr.auto_snapshot()
        ok(f"Auto-snapshot: {sid}" if sid else "No changes, skipped")


def cmd_discover(section: str = "pattern", action: str = "stats",
                 category: Optional[str] = None, mini: Optional[str] = None,
                 project: Optional[str] = None, pattern_name: Optional[str] = None,
                 description: Optional[str] = None, snippet: Optional[str] = None):
    """Cross-project patterns and token economics."""
    from eni.discovery import PatternBroadcaster, TokenTracker

    if section == "pattern":
        bc = PatternBroadcaster()
        if action == "add":
            if not all([mini, project, pattern_name, category, description, snippet]):
                err("Pattern add requires: --mini --project --pattern-name --category --description --snippet")
                return
            pattern = bc.broadcast(mini, project, pattern_name, category, description, snippet)
            ok(f"Broadcast: {pattern.uuid}")
        else:
            stats = bc.stats()
            print(f"\n{C.BOLD}Shared Patterns{C.RST}")
            print(f"  Total: {stats['total_patterns']} patterns, {stats['total_uses']} uses")
            if stats["recent"]:
                print(f"  {C.DIM}Recent:{C.RST}")
                for p in stats["recent"]:
                    print(f"    [{p['category']}] {p['name']} from {p['source']}")
    elif section == "token":
        tt = TokenTracker()
        if action == "reset":
            tt.reset()
            ok("Token tracking reset")
        elif action == "per-mini":
            stats = tt.per_mini_stats()
            for name, s in stats.items():
                print(f"\n  {C.BOLD}{name}{C.RST}")
                print(f"    Calls: {s['calls']} ({s['success_rate']}% success)")
                print(f"    Tokens: {s['total_prompt_tokens']+s['total_completion_tokens']:,} ({s['avg_latency_ms']}ms avg)")
                print(f"    Cost: ${s['total_cost']}")
                print(f"    Models: {', '.join(s['models_used'][:3])}")
        else:
            stats = tt.aggregate_stats()
            print(f"\n{C.BOLD}Token Economics{C.RST}")
            print(f"  Calls: {stats['total_calls']} ({stats['success_rate']}% success)")
            print(f"  Tokens: {stats['total_tokens']:,}")
            print(f"  Cost: ${stats['total_cost_usd']}")
            print(f"  Savings: {stats['estimated_token_savings']:,} tokens (~${stats['estimated_cost_saved']})")
            print(f"  Rate: {stats['calls_per_hour']} calls/hr, {stats['tokens_per_hour']:,} tokens/hr")


# ─── CLI dispatch ───────────────────────────────────────────────────────────

def _try_click():
    """Dispatch using Click if available."""
    try:
        import click

        @click.group(help="ENI Swarm — Unified Coordination CLI", invoke_without_command=True)
        @click.version_option(version="4.0.0", prog_name="eni-swarm")
        @click.pass_context
        def cli(ctx):
            if ctx.invoked_subcommand is None:
                banner()
                click.echo(click.style("Usage:", bold=True) + " eni-swarm <command> [options]\n")
                click.echo("Commands:")
                for cmd_name, cmd_obj in sorted(cli.commands.items()):
                    help_text = cmd_obj.get_short_help_str(limit=50)
                    click.echo(f"  {click.style(cmd_name, fg='cyan'):20s} {help_text}")
                click.echo(f"\nRun {click.style('eni-swarm <command> --help', dim=True)} for per-command options.")

        @cli.command()
        @click.option("--project", help="Project name")
        @click.option("--workers", type=int, default=0, help="Number of workers (0=auto)")
        def start(project, workers):
            """Start the swarm for a project."""
            cmd_start(project=project, workers=workers)

        @cli.command()
        @click.option("--project", help="Project name")
        def stop(project):
            """Stop swarm workers."""
            cmd_stop(project=project)

        @cli.command()
        def status():
            """Show full swarm status."""
            cmd_status()

        @cli.command()
        def heartbeat():
            """Show real-time heartbeat/pulse monitor."""
            cmd_heartbeat()

        @cli.command()
        def launch():
            """Launch visible terminal windows."""
            cmd_launch()

        @cli.command()
        @click.argument("action", type=click.Choice(["show", "edit"]), default="show")
        def config(action):
            """Show or edit swarm config."""
            cmd_config(action=action)

        @cli.group()
        def task():
            """Manage task roster."""
            pass

        @task.command("list")
        def task_list():
            """List all tasks."""
            cmd_task(action="list")

        @task.command("add")
        @click.option("--name", required=True, help="Task name")
        @click.option("--title", help="Task title")
        @click.option("--workdir", default="~", help="Working directory")
        @click.option("--model", default="tencent/hy3:free", help="Model to use")
        @click.option("--task-text", "task", default="", help="Task prompt")
        def task_add(name, title, workdir, model, task):
            """Add a new task."""
            cmd_task(action="add", name=name, title=title, workdir=workdir, model=model, task_text=task)

        @task.command("remove")
        @click.option("--name", required=True, help="Task name to remove")
        def task_remove(name):
            """Remove a task."""
            cmd_task(action="remove", name=name)

        @cli.command()
        @click.option("--follow", "-f", is_flag=True, help="Follow log output")
        @click.option("--mini", help="Show status for a specific mini")
        def logs(follow, mini):
            """View swarm logs."""
            cmd_logs(follow=follow, mini=mini)

        @cli.command()
        def dashboard():
            """Start web dashboard on :8420."""
            cmd_dashboard()

        @cli.command()
        @click.argument("action", type=click.Choice(["start", "stop", "restart", "status"]), default="status")
        def daemon(action):
            """Manage KB daemon."""
            cmd_daemon(action=action)

        @cli.group()
        def sync():
            """Manage peer sync."""
            pass

        @sync.command("once")
        def sync_once():
            """Run one sync cycle."""
            cmd_sync(action="once")

        @sync.command("daemon")
        def sync_daemon():
            """Run sync as daemon."""
            cmd_sync(action="daemon")

        @sync.command("peers")
        def sync_peers():
            """Show peer configuration."""
            cmd_sync(action="peers")

        @sync.command("status")
        def sync_status():
            """Show sync status."""
            cmd_sync(action="status")

        @cli.command()
        @click.argument("file", required=True)
        def compress(file):
            """Compress a file through the pipeline."""
            cmd_compress(file=file)

        @cli.group()
        def glyph():
            """Glyph management."""
            pass

        @glyph.command("list")
        @click.option("--category", help="Filter by category")
        def glyph_list(category):
            """List all glyphs."""
            cmd_glyph(action="list", category=category)

        @glyph.command("allocate")
        @click.option("--name", required=True, help="Glyph name")
        @click.option("--expansion", required=True, help="Expansion text")
        @click.option("--category", default="custom", help="Category")
        def glyph_allocate(name, expansion, category):
            """Allocate a new glyph."""
            cmd_glyph(action="allocate", name=name, expansion=expansion, category=category)

        @glyph.command("expand")
        @click.option("--text", required=True, help="Text with glyph tokens")
        def glyph_expand(text):
            """Expand glyph tokens in text."""
            cmd_glyph(action="expand", text=text)

        @glyph.command("compress")
        @click.option("--text", required=True, help="Text to compress")
        def glyph_compress(text):
            """Compress text with glyphs."""
            cmd_glyph(action="compress", text=text)

        @glyph.command("stats")
        def glyph_stats():
            """Show glyph statistics."""
            cmd_glyph(action="stats")

        @cli.command()
        @click.option("--generations", type=int, default=50, help="Number of generations")
        def evolve(generations):
            """Run compression evolution."""
            cmd_evolve(generations=generations)

        @cli.command()
        @click.option("--workers", type=int, default=4, help="Number of workers")
        def skill_forge(workers):
            """Run skill forge swarm."""
            cmd_skill_forge(workers=workers)

        @cli.command()
        def version():
            """Show ENI Swarm version."""
            cmd_version()

        cli()
        return True

    except ImportError:
        return False


def _argparse_dispatch():
    """Dispatch using argparse (fallback)."""
    import argparse

    parser = argparse.ArgumentParser(
        description="ENI Swarm — Unified Coordination CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="store_true", help="Show version and exit")

    sub = parser.add_subparsers(dest="command", title="commands")

    # start
    p = sub.add_parser("start", help="Start the swarm for a project")
    p.add_argument("--project", help="Project name")
    p.add_argument("--workers", type=int, default=0, help="Number of workers (0=auto)")

    # stop
    p = sub.add_parser("stop", help="Stop swarm workers")
    p.add_argument("--project", help="Project name")

    # status
    sub.add_parser("status", help="Show full swarm status")

    # heartbeat
    sub.add_parser("heartbeat", help="Show real-time heartbeat monitor")

    # launch
    sub.add_parser("launch", help="Launch visible terminal windows")

    # config
    p = sub.add_parser("config", help="Show or edit swarm config")
    p.add_argument("action", nargs="?", choices=["show", "edit"], default="show")

    # task
    p = sub.add_parser("task", help="Manage task roster")
    p.add_argument("action", nargs="?", choices=["list", "add", "remove"], default="list")
    p.add_argument("--name", help="Task name")
    p.add_argument("--title", help="Task title")
    p.add_argument("--workdir", help="Working directory")
    p.add_argument("--model", help="Model to use")
    p.add_argument("--task-text", dest="task_text", help="Task prompt")

    # logs
    p = sub.add_parser("logs", help="View swarm logs")
    p.add_argument("--follow", "-f", action="store_true", help="Follow log output")
    p.add_argument("--mini", help="Show status for a specific mini")

    # dashboard
    sub.add_parser("dashboard", help="Start web dashboard on :8420")

    # daemon
    p = sub.add_parser("daemon", help="Manage KB daemon")
    p.add_argument("action", nargs="?", choices=["start", "stop", "restart", "status"], default="status")

    # sync
    p = sub.add_parser("sync", help="Manage peer sync")
    p.add_argument("action", nargs="?", choices=["once", "daemon", "peers", "status"], default="status")

    # compress
    p = sub.add_parser("compress", help="Compress a file through the pipeline")
    p.add_argument("file", help="Path to file")

    # glyph
    p = sub.add_parser("glyph", help="Glyph management")
    p.add_argument("action", nargs="?", choices=["list", "allocate", "expand", "compress", "stats", "init"], default="list")
    p.add_argument("--name", help="Glyph name")
    p.add_argument("--expansion", help="Expansion text")
    p.add_argument("--category", default="custom", help="Category")
    p.add_argument("--text", help="Text to expand/compress")

    # evolve
    p = sub.add_parser("evolve", help="Run compression evolution")
    p.add_argument("--generations", type=int, default=50, help="Number of generations")

    # skill-forge
    p = sub.add_parser("skill-forge", help="Run skill forge swarm")
    p.add_argument("--workers", type=int, default=4, help="Number of workers")

    # tui — live terminal dashboard
    sub.add_parser("tui", help="Launch live TUI dashboard (Rich)")

    # model — model resolver / auto-fallback
    p = sub.add_parser("model", help="Model management and auto-fallback")
    p.add_argument("action", nargs="?", choices=["list", "resolve", "fail", "success", "add", "reset"],
                   default="list")
    p.add_argument("--model-name", dest="model_name", help="Model name")
    p.add_argument("--code", type=int, default=500, help="HTTP status code")

    # snapshot — save/restore swarm state
    p = sub.add_parser("snapshot", help="Snapshot and restore swarm state")
    p.add_argument("action", nargs="?", choices=["create", "list", "restore", "delete", "prune", "auto"],
                   default="list")
    p.add_argument("--name", "-n", help="Snapshot name")
    p.add_argument("--id", help="Snapshot ID")
    p.add_argument("--keep", type=int, default=10, help="Keep N snapshots (prune)")

    # discover — pattern sharing + token economics
    p = sub.add_parser("discover", help="Cross-project patterns + token economics")
    p.add_argument("section", nargs="?", choices=["pattern", "token"], default="pattern")
    p.add_argument("action", nargs="?", choices=["list", "stats", "summary", "per-mini", "reset", "add"],
                   default="stats")
    p.add_argument("--category", help="Pattern category filter")
    p.add_argument("--mini", help="Mini name")
    p.add_argument("--project", help="Project name")
    p.add_argument("--pattern-name", dest="pattern_name", help="Pattern name")
    p.add_argument("--description", help="Pattern description")
    p.add_argument("--snippet", help="Code snippet")

    # version
    sub.add_parser("version", help="Show ENI Swarm version")

    # assign — dynamic task injection
    p = sub.add_parser("assign", help="Assign a task to an idle builder")
    p.add_argument("task", nargs="?", help="The task to assign")
    p.add_argument("--workdir", "-w", help="Working directory")
    p.add_argument("--mini", "-m", help="Target specific builder")
    p.add_argument("--broadcast", "-b", action="store_true", help="Send to ALL builders")

    # builders — list builder status
    p = sub.add_parser("builders", help="List all builders with status")
    p.add_argument("--watch", "-w", action="store_true", help="Watch mode (refresh every 3s)")

    args = parser.parse_args()

    if args.version or args.command == "version":
        cmd_version()
        return

    if args.command is None:
        banner()
        print(f"{C.BOLD}Usage:{C.RST} eni-swarm <command> [options]")
        print()
        print(f"{C.BOLD}Commands:{C.RST}")
        for choice in sub.choices:
            h = sub.choices[choice].description or ""
            print(f"  {C.CYN}{choice:18s}{C.RST}  {h}")
        print(f"\nRun {C.DIM}eni-swarm <command> --help{C.RST} for per-command options.")
        return

    # Dispatch
    cmd = args.command
    action = getattr(args, "action", None)

    if cmd == "start":
        cmd_start(project=args.project, workers=args.workers)
    elif cmd == "stop":
        cmd_stop(project=args.project)
    elif cmd == "status":
        cmd_status()
    elif cmd == "heartbeat":
        cmd_heartbeat()
    elif cmd == "launch":
        cmd_launch()
    elif cmd == "config":
        cmd_config(action=action)
    elif cmd == "task":
        cmd_task(action=action, name=getattr(args, "name", None),
                  title=getattr(args, "title", None),
                  workdir=getattr(args, "workdir", None),
                  model=getattr(args, "model", None),
                  task_text=getattr(args, "task_text", None))
    elif cmd == "logs":
        cmd_logs(follow=args.follow, mini=args.mini)
    elif cmd == "dashboard":
        cmd_dashboard()
    elif cmd == "daemon":
        cmd_daemon(action=action)
    elif cmd == "sync":
        cmd_sync(action=action)
    elif cmd == "compress":
        cmd_compress(file=args.file)
    elif cmd == "glyph":
        cmd_glyph(action=action, name=getattr(args, "name", None),
                  expansion=getattr(args, "expansion", None),
                  category=getattr(args, "category", "custom"),
                  text=getattr(args, "text", None))
    elif cmd == "evolve":
        cmd_evolve(generations=args.generations)
    elif cmd == "skill-forge":
        cmd_skill_forge(workers=args.workers)
    elif cmd == "tui":
        cmd_tui()
    elif cmd == "model":
        cmd_model(action=action, model_name=args.model_name, code=args.code)
    elif cmd == "snapshot":
        cmd_snapshot(action=action, name=args.name, snapshot_id=args.id,
                     keep=args.keep)
    elif cmd == "discover":
        cmd_discover(section=args.section, action=action,
                     category=args.category, mini=args.mini,
                     project=args.project, pattern_name=args.pattern_name,
                     description=args.description, snippet=args.snippet)
    elif cmd == "version":
        cmd_version()
    else:
        err("Unknown command: {}", cmd)
        sys.exit(1)


def main():
    """Main entry point for eni-swarm CLI."""
    if not _try_click():
        _argparse_dispatch()


if __name__ == "__main__":
    main()