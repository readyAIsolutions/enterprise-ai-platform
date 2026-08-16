#!/usr/bin/env python3
"""
ENI Master Driver v5.0 — On-Demand Swarm Coordination
======================================================
Single coordination process that:
  1. Reads task rosters (50 builders + coordinators)
  2. Tracks which minis have pending work
  3. Spawns 'hermes run' ON-DEMAND — no persistent agent processes
  4. Limits concurrency to max_workers (default 6)
  5. Reads STATUS files, routes replies via FIFO
  6. Writes MASTER_STATUS.md + builder logs for dashboard
  7. Self-heals: detects stalled minis, respawns on crash

KEY DIFFERENCE from v4: minis are NOT persistent 'hermes chat' processes.
They are logical slots. When work is assigned, the master spawns
'hermes run --yolo' for that mini, waits for completion, then the mini
goes idle. Zero CPU when nothing is building.

Run:  python3 -m eni.master_driver [--config PATH] [--interval SEC] [--workers N]
"""
from __future__ import annotations

import os
import sys
import json
import time
import re
import signal
import subprocess
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
TASKS_BUILD = CONFIG_DIR / "eni_build_tasks.json"
TASKS_HERSELF = CONFIG_DIR / "eni_herself_tasks.json"
SWARM_DIR = ROOT / "tasks" / "swarm"
STATUS_DIR = ROOT / "tasks" / "status"
LOG_DIR = Path.home() / ".cache" / "eni_swarm" / "builder_logs"
FIFO_DIR = Path("/tmp")
STATE_FILE = Path.home() / ".cache" / "eni_swarm" / "master_state.json"
LOG_FILE = Path.home() / ".cache" / "eni_swarm" / "coordination.log"
CONFIG_WATCH_FILE = Path.home() / ".hermes" / "config.yaml"

for d in (SWARM_DIR, STATUS_DIR, STATE_FILE.parent, LOG_FILE.parent, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ─── Global model/provider — updated by config watcher ──────────────────────
CURRENT_MODEL = "free-router"
CURRENT_PROVIDER = "free-router"
MODEL_LOCK = threading.Lock()

# ─── Live Context Injected by LO ───────────────────────────────────────────
LIVE_CONTEXT: Dict[str, str] = {
    "DEMIURGE_OANDA": (
        "LO confirms a REAL OANDA test+live account exists and is being built — use it. "
        "Find OANDA_TOKEN / OANDA_ACCOUNT_ID in env or /run/media/hunter/DEMIURGE/.env."
    ),
    "DEMIURGE_MTF": (
        "LO reaffirms: use ANY/ALL timeframes (M1..W1) as STRUCTURE/BIAS filters — never drop H4."
    ),
    "DEMIURGE_NEWS": (
        "LO: the current news source is NOT top-tier and may be noise we overfit to."
    ),
    "DEMIURGE_FEATURES": (
        "LO: the '2 entries' setting is a held-over override flag, NOT an ablation-proven optimum."
    ),
    "DEMIURGE_GATE": (
        "LO: gate's fill>=0.70 is fragile (mean 0.675, 6/12 folds below). Tighten it."
    ),
    "DEMIURGE_AUTOML": (
        "LO: auto-learn + swarm must be PUT TO USE, not just built."
    ),
    "DEMIURGE_RISK": (
        "LO: FTMO caps are 5-10% max DD. Build vol-scaled sizing AND a HARD max-daily-loss halt."
    ),
    "LUMEN": "Push to shippable, Steam-store-ready polish.",
    "DEMIURGE-3D": "Advance the DEMIURGE-3D app per its own plan.",
    "DEMIURGE-3D-FRONTEND": "Advance the DEMIURGE-3D frontend (React + Three.js).",
    "DEMIURGE-3D-BACKEND": "Harden the DEMIURGE-3D backend.",
}


# ─── Protocol ───────────────────────────────────────────────────────────────
PROTOCOL_TEMPLATE = """PROTOCOL: after every build step overwrite {status_file} with:
  [DONE|IN-PROGRESS|BLOCKED] <one line>
  verified=<...>
  blocker=<...>
  next=<...>
The master reads this to coordinate you — keep it current.
"""


# ─── Data Classes ──────────────────────────────────────────────────────────
@dataclass
class MiniSlot:
    """A logical builder slot — NOT a persistent process."""
    name: str
    title: str
    workdir: str
    model: str
    provider: str
    task: str
    status_file: str = ""
    last_mtime: float = 0.0
    last_reply: str = ""
    cycles_since_reply: int = 0
    pending_task: Optional[str] = None
    active: bool = False  # Currently executing hermes run
    task_count: int = 0

    def __post_init__(self):
        if not self.status_file:
            m = re.search(r"Write (STATUS_\w+\.md)", self.task)
            self.status_file = m.group(1) if m else f"STATUS_{self.name}.md"


@dataclass
class MasterState:
    minis: Dict[str, dict] = field(default_factory=dict)
    cycle: int = 0
    updated: str = ""
    model: str = "free-router"
    provider: str = "free-router"

    def save(self):
        STATE_FILE.write_text(json.dumps({
            "minis": self.minis,
            "cycle": self.cycle,
            "updated": self.updated,
            "model": self.model,
            "provider": self.provider,
        }, indent=2))

    @classmethod
    def load(cls) -> "MasterState":
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text())
                return cls(**{k: data.get(k, v if k != "minis" else {})
                               for k, v in cls.__dataclass_fields__.items()
                               if k != "minis" or isinstance(data.get(k), dict)})
            except Exception:
                pass
        return cls()


# ─── Utility ───────────────────────────────────────────────────────────────
def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with LOG_FILE.open("a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def read_status(path: Path) -> str:
    try:
        return path.read_text()
    except Exception:
        return ""


def parse_state(txt: str) -> str:
    s = txt.upper()
    if "BLOCKED" in s: return "BLOCKED"
    if "IN-PROGRESS" in s or "IN PROGRESS" in s: return "IN-PROGRESS"
    if "DONE" in s or "[DONE]" in s: return "DONE"
    if "IDLE" in s or "[IDLE]" in s: return "IDLE"
    m = re.search(r'\[(?:state|STATUS)\s*:\s*(\w[\w\s-]*)\]', txt)
    if m:
        st = m.group(1).upper().strip()
        if "BLOCK" in st: return "BLOCKED"
        if "PROGRESS" in st: return "IN-PROGRESS"
        if "DONE" in st: return "DONE"
        if "IDLE" in st: return "IDLE"
        return st
    return "UNKNOWN"


def extract_blocker(txt: str) -> str:
    for line in txt.splitlines():
        if line.strip().lower().startswith("blocker"):
            return line.split("=", 1)[-1].strip()
    return ""


def is_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def ensure_fifo(path: str):
    p = Path(path)
    try:
        if p.exists() and not p.is_fifo():
            p.unlink()
        if not p.exists():
            os.mkfifo(p, 0o666)
    except Exception as e:
        log(f"[FIFO] Failed to create {path}: {e}")


def send_fifo(path: str, msg: str) -> bool:
    try:
        fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, (msg + "\n").encode())
            return True
        finally:
            os.close(fd)
    except OSError:
        return False


def write_builder_log(name: str, text: str):
    """Write builder output for dashboard live feed."""
    try:
        ts = datetime.now().strftime("%H:%M:%S")
        with open(LOG_DIR / f"{name}.log", "a") as f:
            f.write(f"[{ts}] [{name}] {text[:500]}\n")
    except Exception:
        pass


# ─── Task Loading ──────────────────────────────────────────────────────────
def load_tasks() -> List[MiniSlot]:
    tasks = []
    for path in (TASKS_BUILD, TASKS_HERSELF):
        if not path.exists():
            log(f"[WARN] Task file not found: {path}")
            continue
        data = json.loads(path.read_text())
        for t in data.get("tasks", []):
            tasks.append(MiniSlot(
                name=t["name"],
                title=t.get("title", t["name"]),
                workdir=os.path.expanduser(t.get("workdir", "~")),
                model=t.get("model", CURRENT_MODEL),
                provider=t.get("provider", CURRENT_PROVIDER),
                task=t.get("task", ""),
            ))
    return tasks


# ─── Hermes Run Execution ──────────────────────────────────────────────────
# Try to import PromptForge for maximum prompt enhancement
try:
    from eni.prompt_forge import enhance_for_builder, PROMPTFORGE_AVAILABLE
except ImportError:
    PROMPTFORGE_AVAILABLE = False
    enhance_for_builder = None

def execute_mini_task(mini: MiniSlot, task_prompt: str) -> bool:
    """
    Execute 'hermes run' for a mini. Returns True on success.
    This is the core execution engine — no persistent process.
    NOW WITH PROMPTFORGE: Maximum prompt enhancement for every task.
    """
    global CURRENT_MODEL, CURRENT_PROVIDER

    with MODEL_LOCK:
        model = CURRENT_MODEL
        provider = CURRENT_PROVIDER

    workdir = Path(mini.workdir).expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    # ─── PROMPTFORGE: Enhance the prompt with ALL context ────────────────────
    if PROMPTFORGE_AVAILABLE and enhance_for_builder:
        try:
            result = enhance_for_builder(mini.name, task_prompt, model=model)
            full_prompt = result.enhanced
            write_builder_log(mini.name, f"[PROMPTFORGE] Enhanced {len(task_prompt)} -> {len(full_prompt)} chars ({result.metadata.get('compression_ratio', 0):.1f}x)")
        except Exception as e:
            write_builder_log(mini.name, f"[PROMPTFORGE] Enhancement failed: {e}, using base prompt")
            # Fallback to basic prompt building
            live = LIVE_CONTEXT.get(mini.name, "")
            proto = PROTOCOL_TEMPLATE.format(status_file=mini.status_file)
            full_prompt = f"{live}\n\n{task_prompt}\n\n{proto}"
    else:
        # Original basic prompt building
        live = LIVE_CONTEXT.get(mini.name, "")
        proto = PROTOCOL_TEMPLATE.format(status_file=mini.status_file)
        full_prompt = f"{live}\n\n{task_prompt}\n\n{proto}"

    write_builder_log(mini.name, f"EXEC: {task_prompt[:200]}")
    log(f"[EXEC] {mini.name} → hermes -z -m {model} --provider {provider}")

    env = os.environ.copy()
    env["ENI_AGENT_NAME"] = mini.name
    env["ENI_WORKDIR"] = str(workdir)
    env["PATH"] = f"/home/hunter/.local/bin:/home/hunter/bin:{env.get('PATH', '')}"

    cmd = [
        "hermes", "-z", full_prompt,
        "-m", model,
        "--provider", provider,
        "--yolo",
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(workdir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # Stream output to builder log for live dashboard visibility
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                write_builder_log(mini.name, line[:400])

        proc.wait(timeout=600)
        ok = proc.returncode == 0
        write_builder_log(mini.name, f"DONE (exit={proc.returncode})" if ok else f"FAILED (exit={proc.returncode})")
        log(f"[EXEC] {mini.name} completed (exit={proc.returncode})")
        return ok

    except subprocess.TimeoutExpired:
        proc.kill()
        write_builder_log(mini.name, "TIMEOUT (600s)")
        log(f"[EXEC] {mini.name} TIMEOUT")
        return False
    except Exception as e:
        write_builder_log(mini.name, f"ERROR: {e}")
        log(f"[EXEC] {mini.name} ERROR: {e}")
        return False


# ─── Config Watcher ─────────────────────────────────────────────────────────
def watch_hermes_config():
    """Background thread: watches ~/.hermes/config.yaml for model/provider changes."""
    global CURRENT_MODEL, CURRENT_PROVIDER

    last_mtime = 0
    while True:
        try:
            if CONFIG_WATCH_FILE.exists():
                mtime = CONFIG_WATCH_FILE.stat().st_mtime
                if mtime > last_mtime:
                    last_mtime = mtime
                    text = CONFIG_WATCH_FILE.read_text()

                    # Parse model.default and model.provider
                    import yaml
                    try:
                        cfg = yaml.safe_load(text)
                        model_cfg = cfg.get("model", {})
                        new_model = model_cfg.get("default", CURRENT_MODEL)
                        new_provider = model_cfg.get("provider", CURRENT_PROVIDER)

                        if new_model != CURRENT_MODEL or new_provider != CURRENT_PROVIDER:
                            with MODEL_LOCK:
                                CURRENT_MODEL = new_model
                                CURRENT_PROVIDER = new_provider
                            log(f"[CONFIG] Model changed → {new_model} @ {new_provider}")
                    except Exception:
                        pass  # YAML parse failed, ignore
        except Exception:
            pass
        time.sleep(5)


# ─── Craft Reply ───────────────────────────────────────────────────────────
def craft_reply(mini: MiniSlot, status_txt: str, state: str) -> str:
    live = LIVE_CONTEXT.get(mini.name, "")
    proto = PROTOCOL_TEMPLATE.format(status_file=mini.status_file)

    if not mini.pending_task:
        return ""  # Nothing to say

    if not status_txt:
        return f"{live}\n\n{proto}\nWrite {mini.status_file} and begin building."

    if state == "BLOCKED":
        blk = extract_blocker(status_txt)
        return f"You flagged BLOCKED{' : ' + blk if blk else ''}. Options: (a) scaffold, (b) request file, (c) make design call & proceed."

    if state == "DONE":
        return "Marked DONE — verify with command output, then take NEXT phase."

    if state == "IN-PROGRESS":
        return "In progress — name the NEXT deliverable and verify it."

    return f"Re-write {mini.status_file} with [DONE|IN-PROGRESS|BLOCKED]."


# ─── Write MASTER_STATUS.md ────────────────────────────────────────────────
def write_master_status(minis: Dict[str, MiniSlot], cycle: int):
    lines = [
        f"# MASTER_STATUS.md — ENI Swarm v5.0 (On-Demand)",
        f"## Cycle {cycle} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Model**: {CURRENT_MODEL} @ {CURRENT_PROVIDER}",
        f"",
        f"| Mini | State | Tasks Done | Last Update | Workdir |",
        f"|------|-------|------------|-------------|---------|",
    ]

    alerts = []
    for name in sorted(minis.keys()):
        m = minis[name]
        status_path = Path(m.workdir).expanduser() / m.status_file
        txt = read_status(status_path)
        st = parse_state(txt)
        mtime = datetime.fromtimestamp(status_path.stat().st_mtime).strftime("%H:%M:%S") if status_path.exists() else "never"
        lines.append(f"| {name} | {st} | {m.task_count} | {mtime} | {m.workdir} |")

        if st == "BLOCKED":
            blk = extract_blocker(txt)
            alerts.append(f"🔴 **{name} BLOCKED**: {blk or 'no blocker specified'}")
        elif m.cycles_since_reply > 16:
            alerts.append(f"🟡 **{name} QUIET**: {m.cycles_since_reply} cycles silent")

    lines.append("")
    lines.append("## ALERTS")
    if alerts:
        for a in alerts:
            lines.append(f"- {a}")
    else:
        lines.append("- None — all minis healthy")

    lines.append("")
    lines.append("## LIVE CONTEXT INJECTED")
    for k, v in LIVE_CONTEXT.items():
        lines.append(f"- **{k}**: {v[:120]}...")

    (STATUS_DIR / "MASTER_STATUS.md").write_text("\n".join(lines))


# ─── Main Loop ─────────────────────────────────────────────────────────────
def main_loop(interval: int = 30, max_workers: int = 6):
    log("=" * 60)
    log(f"[MASTER] ENI Master Driver v5.0 starting (on-demand, max_workers={max_workers})")
    log(f"[MASTER] Model: {CURRENT_MODEL} @ {CURRENT_PROVIDER}")
    log("=" * 60)

    # Start config watcher thread
    watcher = threading.Thread(target=watch_hermes_config, daemon=True)
    watcher.start()

    tasks = load_tasks()
    minis = {t.name: t for t in tasks if t.name != "MASTER"}
    log(f"[MASTER] Loaded {len(minis)} logical minis: {', '.join(sorted(minis)[:10])}...")

    state = MasterState.load()
    for name, mini in minis.items():
        if name in state.minis:
            saved = state.minis[name]
            mini.last_mtime = saved.get("mtime", 0)
            mini.cycles_since_reply = saved.get("cycles", 0)
            mini.task_count = saved.get("task_count", 0)

    executor = ThreadPoolExecutor(max_workers=max_workers)
    cycle = state.cycle

    try:
        while True:
            cycle += 1
            log(f"[CYCLE {cycle}] Scanning {len(minis)} minis...")

            # Find minis that need work and aren't currently executing
            pending = []
            for name, mini in minis.items():
                if mini.active:
                    continue

                status_path = Path(mini.workdir).expanduser() / mini.status_file
                txt = read_status(status_path)
                st = parse_state(txt)

                # Minis that need their initial task or have pending FIFO work
                if mini.pending_task or st == "UNKNOWN" or mini.cycles_since_reply == 0:
                    task = mini.pending_task or mini.task
                    pending.append((mini, task))
                    mini.pending_task = None
                    mini.active = True
                    mini.cycles_since_reply += 1
                else:
                    mini.cycles_since_reply += 1

            # Execute pending minis (up to max_workers concurrently)
            if pending:
                log(f"[CYCLE {cycle}] Dispatching {len(pending)} tasks (max {max_workers} concurrent)...")
                futures = {}
                for mini, task in pending:
                    fut = executor.submit(execute_mini_task, mini, task)
                    futures[fut] = mini

                for fut in as_completed(futures):
                    mini = futures[fut]
                    mini.active = False
                    try:
                        ok = fut.result()
                        if ok:
                            mini.task_count += 1
                            mini.cycles_since_reply = 0
                            mini.last_mtime = time.time()
                    except Exception as e:
                        log(f"[EXEC] {mini.name} exception: {e}")

            # Check for FIFO messages (new task injections)
            for name, mini in minis.items():
                if mini.active:
                    continue
                fifo_path = FIFO_DIR / f"eni_ctl_{name}"
                if fifo_path.exists():
                    try:
                        fd = os.open(str(fifo_path), os.O_RDONLY | os.O_NONBLOCK)
                        try:
                            import select
                            ready, _, _ = select.select([fd], [], [], 0.1)
                            if ready:
                                data = os.read(fd, 4096)
                                if data:
                                    msg = data.decode().strip()
                                    if msg and len(msg) > 10:
                                        mini.pending_task = msg
                                        log(f"[FIFO] {name} received new task: {msg[:100]}...")
                        finally:
                            os.close(fd)
                    except OSError:
                        pass

            # Update state
            state.cycle = cycle
            state.model = CURRENT_MODEL
            state.provider = CURRENT_PROVIDER
            state.updated = datetime.now().isoformat()
            state.minis = {
                n: {
                    "mtime": m.last_mtime,
                    "cycles": m.cycles_since_reply,
                    "active": m.active,
                    "task_count": m.task_count,
                }
                for n, m in minis.items()
            }
            state.save()

            # Write master status
            write_master_status(minis, cycle)

            log(f"[CYCLE {cycle}] Done. Active: {sum(1 for m in minis.values() if m.active)}. Sleeping {interval}s...")
            log("-" * 60)
            time.sleep(interval)

    except KeyboardInterrupt:
        log("[MASTER] Shutdown requested")
    finally:
        executor.shutdown(wait=False)
        log("[MASTER] Stopped")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ENI Master Driver v5.0")
    parser.add_argument("--config", type=Path, help="Config directory")
    parser.add_argument("--interval", type=int, default=30, help="Coordination interval seconds")
    parser.add_argument("--workers", type=int, default=6, help="Max concurrent hermes run processes")
    args = parser.parse_args()

    global CONFIG_DIR, TASKS_BUILD, TASKS_HERSELF
    if args.config:
        CONFIG_DIR = args.config
        TASKS_BUILD = CONFIG_DIR / "eni_build_tasks.json"
        TASKS_HERSELF = CONFIG_DIR / "eni_herself_tasks.json"

    main_loop(args.interval, args.workers)


if __name__ == "__main__":
    main()