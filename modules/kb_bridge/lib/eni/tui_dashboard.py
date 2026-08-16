#!/usr/bin/env python3
"""
ENI Swarm TUI Dashboard — Real-Time Terminal Monitor
=====================================================
Live display of all mini agents, system health, compression stats,
and coordination feed. Uses Rich for beautiful terminal rendering.

Launch:  eni-swarm tui   or   python3 -m eni.tui_dashboard
"""
from __future__ import annotations

import os
import sys
import json
import time
import signal
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Rich imports
try:
    from rich.live import Live
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.text import Text
    from rich.console import Console, Group
    from rich.align import Align
    from rich.columns import Columns
    from rich.box import ROUNDED, HEAVY, SIMPLE
    from rich.progress import Progress, BarColumn, TextColumn, SpinnerColumn
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# Project paths
ROOT = Path(__file__).resolve().parents[2]  # ENI_Swarm_NEW
LIB = ROOT / "lib"
sys.path.insert(0, str(LIB))

STATE_FILE = Path.home() / ".cache" / "eni_swarm" / "master_state.json"
STATUS_DIR = ROOT / "tasks" / "status"
CONFIG_DIR = ROOT / "config"
LOG_FILE = Path.home() / ".cache" / "eni_swarm" / "coordination.log"

VERSION = "4.0.0"

# ─── Data Collection ────────────────────────────────────────────────────────

def read_state() -> Dict[str, Any]:
    """Read master state from filesystem."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"minis": {}, "cycle": 0, "updated": ""}


def read_status(mini_name: str) -> str:
    """Read a mini's status file."""
    sf = STATUS_DIR / f"STATUS_{mini_name}.md"
    if sf.exists():
        try:
            return sf.read_text()
        except Exception:
            pass
    return ""


def read_logs(count: int = 10) -> List[str]:
    """Read recent coordination logs."""
    if LOG_FILE.exists():
        try:
            lines = LOG_FILE.read_text().strip().splitlines()
            return lines[-count:]
        except Exception:
            pass
    return ["No logs yet."]


def check_daemon(port: int = 8765) -> bool:
    """Check if KB daemon is running."""
    import socket
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
        s.close()
        return True
    except Exception:
        return False


def check_sync(port: int = 8766) -> bool:
    """Check if sync daemon is running."""
    import socket
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
        s.close()
        return True
    except Exception:
        return False


def check_master() -> bool:
    """Check if master driver is running."""
    pid_file = Path.home() / ".cache" / "eni_swarm" / "master_driver.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            return True
        except (OSError, ValueError):
            pass
    return False


def load_task_config() -> List[Dict]:
    """Load task roster from config."""
    tasks = []
    for cfg in ["eni_build_tasks.json", "eni_herself_tasks.json"]:
        path = CONFIG_DIR / cfg
        if path.exists():
            try:
                data = json.loads(path.read_text())
                tasks.extend(data.get("tasks", []))
            except Exception:
                pass
    return tasks


def fmt_age(ts: float) -> str:
    """Format timestamp as human-readable age."""
    if not ts:
        return "never"
    age = time.time() - ts
    if age < 60:
        return f"{age:.0f}s"
    elif age < 3600:
        return f"{age/60:.0f}m"
    return f"{age/3600:.1f}h"


def parse_state_short(txt: str) -> str:
    """Quick parse of status state."""
    s = txt.upper()
    if "BLOCKED" in s:
        return "BLOCKED"
    if "IN-PROGRESS" in s or "IN PROGRESS" in s:
        return "IN-PROGRESS"
    if "DONE" in s:
        return "DONE"
    return "IDLE"


# ─── TUI Dashboard ──────────────────────────────────────────────────────────

class EniTuiDashboard:
    """Rich-based terminal dashboard for ENI Swarm."""

    def __init__(self):
        if not RICH_AVAILABLE:
            print("Rich library not available. Install: pip install rich")
            sys.exit(1)

        self.console = Console()
        self.running = True
        self.cycle = 0
        self.tasks = load_task_config()
        self.task_names = {t["name"]: t for t in self.tasks}
        self.last_state = {}

    def make_layout(self) -> Layout:
        """Create the main dashboard layout."""
        layout = Layout()

        layout.split(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=6),
        )

        layout["body"].split_row(
            Layout(name="minis", ratio=3),
            Layout(name="sidebar", ratio=2),
        )

        layout["sidebar"].split(
            Layout(name="health"),
            Layout(name="logs"),
        )

        return layout

    def build_header(self, state: Dict) -> Panel:
        """Build the header panel."""
        cycle = state.get("cycle", 0)
        updated = state.get("updated", "never")
        if updated:
            try:
                dt = datetime.fromisoformat(updated)
                updated = dt.strftime("%H:%M:%S")
            except Exception:
                pass

        title = Text("ENI SWARM — LIVE DASHBOARD", style="bold cyan")
        subtitle = Text(
            f"v{VERSION}   │   Cycle {cycle}   │   Updated {updated}   │   "
            f"Minis: {len(self.tasks)} configured",
            style="dim"
        )

        return Panel(
            Group(title, subtitle),
            box=HEAVY,
            border_style="cyan",
            padding=(0, 2),
        )

    def build_mini_table(self, state: Dict) -> Panel:
        """Build the mini agent status table."""
        table = Table(
            box=SIMPLE,
            expand=True,
            show_header=True,
            header_style="bold",
        )
        table.add_column("Mini", style="cyan", width=20, no_wrap=True)
        table.add_column("State", width=10)
        table.add_column("Project", style="dim", width=14)
        table.add_column("Model", style="blue", width=16)
        table.add_column("Age", width=6, justify="right")
        table.add_column("Silent", width=6, justify="right")
        table.add_column("PID", width=6, justify="right")

        minis = state.get("minis", {})
        for name in sorted(minis.keys()):
            m = minis[name]
            alive = m.get("alive", False)
            pid = m.get("pid", 0)
            cycles_silent = m.get("cycles", 0)
            mtime = m.get("mtime", 0)
            age = fmt_age(mtime)

            # Read status file for state
            txt = read_status(name)
            st = parse_state_short(txt)

            # Task info
            task = self.task_names.get(name, {})
            workdir_name = Path(task.get("workdir", "~")).name if task.get("workdir") else "—"
            model_short = task.get("model", "—").split("/")[-1] if task.get("model") else "—"

            # Style
            if not alive:
                state_style = "red"
                state_icon = "⚫ DEAD"
            elif st == "BLOCKED":
                state_style = "yellow"
                state_icon = "🟡 BLKD"
            elif st == "DONE":
                state_style = "green"
                state_icon = "🟢 DONE"
            elif st == "IN-PROGRESS":
                state_style = "bright_cyan"
                state_icon = "🔵 PROG"
            else:
                state_style = "dim"
                state_icon = "⚪ IDLE"

            # Silent warning
            silent_style = "red" if cycles_silent > 6 else ("yellow" if cycles_silent > 3 else "green")

            table.add_row(
                name,
                f"[{state_style}]{state_icon}[/{state_style}]",
                workdir_name,
                model_short,
                age,
                f"[{silent_style}]{cycles_silent}[/{silent_style}]",
                str(pid) if pid else "—",
            )

        # Compute summary
        total = len(minis)
        alive_count = sum(1 for m in minis.values() if m.get("alive"))
        done_count = sum(1 for n in minis if parse_state_short(read_status(n)) == "DONE")
        blocked_count = sum(1 for n in minis if parse_state_short(read_status(n)) == "BLOCKED")
        progress_count = sum(1 for n in minis if parse_state_short(read_status(n)) == "IN-PROGRESS")

        summary = Text(
            f"Total: {total}   Alive: [green]{alive_count}[/green]   "
            f"Done: [green]{done_count}[/green]   "
            f"In Progress: [cyan]{progress_count}[/cyan]   "
            f"Blocked: [yellow]{blocked_count}[/yellow]",
            style="bold",
        )

        return Panel(
            Group(summary, table),
            title="[bold]Builder Minis[/bold]",
            border_style="cyan",
            box=ROUNDED,
        )

    def build_health_panel(self, state: Dict) -> Panel:
        """Build the system health panel."""
        daemon_ok = check_daemon()
        sync_ok = check_sync()
        master_ok = check_master()

        health_lines = []
        health_lines.append(
            f"{'🟢' if daemon_ok else '🔴'} KB Daemon  {'(port 8765)' if daemon_ok else ''}"
        )
        health_lines.append(
            f"{'🟢' if sync_ok else '🔴'} Sync Server{' (port 8766)' if sync_ok else ''}"
        )
        health_lines.append(
            f"{'🟢' if master_ok else '🔴'} Master Driver"
        )

        # Show last MASTER_STATUS if available
        master_status = STATUS_DIR / "MASTER_STATUS.md"
        if master_status.exists():
            try:
                content = master_status.read_text()
                # Extract alerts section
                lines = content.splitlines()
                in_alerts = False
                alerts = []
                for line in lines:
                    if "## ALERTS" in line:
                        in_alerts = True
                        continue
                    if in_alerts and line.startswith("##"):
                        break
                    if in_alerts and line.strip().startswith("-"):
                        alerts.append(line.strip())
                if alerts:
                    health_lines.append("")
                    health_lines.append("[bold yellow]Alerts:[/bold yellow]")
                    health_lines.extend(alerts[:5])
            except Exception:
                pass

        return Panel(
            "\n".join(health_lines),
            title="[bold]System Health[/bold]",
            border_style="green" if daemon_ok else "red",
            box=ROUNDED,
        )

    def build_logs_panel(self) -> Panel:
        """Build the recent logs panel."""
        logs = read_logs(8)
        return Panel(
            "\n".join(f"[dim]{l}[/dim]" for l in logs),
            title="[bold]Coordination Log[/bold]",
            border_style="blue",
            box=ROUNDED,
        )

    def build_footer(self, state: Dict) -> Panel:
        """Build the footer with controls help."""
        help_text = (
            "[bold]Controls:[/bold] "
            "[cyan]q[/cyan] Quit  │  "
            "[cyan]r[/cyan] Refresh  │  "
            "[cyan]s[/cyan] Status files  │  "
            "[cyan]l[/cyan] View logs  │  "
            "[cyan]t[/cyan] Tasks"
        )
        return Panel(help_text, box=SIMPLE, border_style="dim")

    def run(self):
        """Run the dashboard loop."""
        self.console.clear()

        with Live(self.console, refresh_per_second=2, screen=True) as live:
            while self.running:
                self.cycle += 1
                state = read_state()
                self.last_state = state

                # Build layout
                layout = self.make_layout()
                layout["header"].update(self.build_header(state))
                layout["minis"].update(self.build_mini_table(state))
                layout["health"].update(self.build_health_panel(state))
                layout["logs"].update(self.build_logs_panel())
                layout["footer"].update(self.build_footer(state))

                live.update(layout)
                time.sleep(2)


def main():
    """Entry point for TUI dashboard."""
    if not RICH_AVAILABLE:
        print("ERROR: Rich library required. Install: pip install rich")
        sys.exit(1)

    dashboard = EniTuiDashboard()
    try:
        dashboard.run()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    except Exception as e:
        print(f"Dashboard error: {e}")
        raise


if __name__ == "__main__":
    main()
