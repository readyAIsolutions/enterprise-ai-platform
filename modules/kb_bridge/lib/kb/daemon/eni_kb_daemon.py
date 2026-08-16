"""
ENI Knowledge Base Daemon — Core Service
=========================================
Runs the MCP servers, LSP server, sync daemon, and status aggregation.
Managed via systemd: systemctl --user start eni-kb
"""
from __future__ import annotations

import os
import sys
import json
import time
import signal
import logging
import threading
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler

KB_ROOT = Path(os.environ.get("ENI_KB_ROOT", "/home/hunter/.eni/kb"))
KB_ROOT.mkdir(parents=True, exist_ok=True)

LOG_DIR = KB_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "eni_kb_daemon.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("eni_kb_daemon")


class ServiceManager:
    """Manages subprocess services."""

    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}
        self.running = False

    def start_service(self, name: str, cmd: List[str], cwd: Optional[Path] = None, env: Optional[Dict] = None):
        if name in self.processes and self.processes[name].poll() is None:
            log.info(f"Service {name} already running")
            return

        full_env = os.environ.copy()
        full_env["PYTHONPATH"] = f"{KB_ROOT}:{full_env.get('PYTHONPATH', '')}"
        if env:
            full_env.update(env)

        log.info(f"Starting service: {name} -> {' '.join(cmd)}")
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else str(KB_ROOT),
            env=full_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.processes[name] = proc

        # Log output in background
        threading.Thread(target=self._log_output, args=(name, proc), daemon=True).start()

    def _log_output(self, name: str, proc: subprocess.Popen):
        for line in proc.stdout or []:
            log.debug(f"[{name}] {line.rstrip()}")

    def stop_service(self, name: str):
        proc = self.processes.get(name)
        if proc:
            log.info(f"Stopping service: {name}")
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            del self.processes[name]

    def stop_all(self):
        for name in list(self.processes.keys()):
            self.stop_service(name)

    def status(self) -> Dict[str, dict]:
        result = {}
        for name, proc in self.processes.items():
            code = proc.poll()
            result[name] = {
                "running": code is None,
                "pid": proc.pid,
                "exit_code": code,
            }
        return result


def init_databases():
    """Initialize SQLite databases for skills, patterns, and sessions tracking."""
    import sqlite3

    db_dir = KB_ROOT
    db_dir.mkdir(parents=True, exist_ok=True)

    # Skills DB
    skills_db = db_dir / "skills.db"
    conn = sqlite3.connect(str(skills_db))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS skills (
            skill_id TEXT PRIMARY KEY,
            glyph TEXT NOT NULL UNIQUE,
            verb TEXT NOT NULL,
            noun TEXT NOT NULL,
            description TEXT,
            dsl_spec TEXT NOT NULL,
            mcp_schema TEXT NOT NULL,
            lsp_capability TEXT NOT NULL,
            execution_mode TEXT NOT NULL,
            entrypoint TEXT,
            python_handler TEXT,
            http_endpoint TEXT,
            wenyan_hash TEXT NOT NULL,
            rtk_hash TEXT NOT NULL,
            pxpipe_png BLOB,
            created_at INTEGER DEFAULT (strftime('%s','now')),
            updated_at INTEGER DEFAULT (strftime('%s','now')),
            pattern_signature TEXT,
            usage_count INTEGER DEFAULT 0,
            fitness REAL DEFAULT 0.0
        );
        CREATE INDEX IF NOT EXISTS idx_skills_verb_noun ON skills(verb, noun);
        CREATE INDEX IF NOT EXISTS idx_skills_glyph ON skills(glyph);
        CREATE INDEX IF NOT EXISTS idx_skills_pattern ON skills(pattern_signature);

        CREATE TABLE IF NOT EXISTS patterns (
            signature TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            verb TEXT NOT NULL,
            noun TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            params TEXT NOT NULL,
            required TEXT NOT NULL,
            example TEXT,
            execution_mode TEXT NOT NULL,
            entrypoint TEXT,
            python_handler TEXT,
            http_endpoint TEXT,
            source_files TEXT NOT NULL,
            success_count INTEGER DEFAULT 0,
            failure_count INTEGER DEFAULT 0,
            frequency INTEGER DEFAULT 1,
            last_seen INTEGER DEFAULT (strftime('%s','now')),
            created_at INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE INDEX IF NOT EXISTS idx_patterns_verb_noun ON patterns(verb, noun);
        CREATE INDEX IF NOT EXISTS idx_patterns_category ON patterns(category);

        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            start_time INTEGER,
            end_time INTEGER,
            tasks_completed INTEGER DEFAULT 0,
            tokens_saved INTEGER DEFAULT 0,
            compression_ratio REAL DEFAULT 1.0
        );
    """)
    conn.commit()
    conn.close()
    log.info(f"Skills database initialized: {skills_db}")

    # Sessions / observed tasks DB
    sessions_db = db_dir / "sessions.db"
    conn = sqlite3.connect(str(sessions_db))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS observed_tasks (
            task_id TEXT PRIMARY KEY,
            timestamp INTEGER NOT NULL,
            description TEXT,
            tools_used TEXT NOT NULL,
            commands_run TEXT NOT NULL,
            file_operations TEXT NOT NULL,
            success INTEGER NOT NULL,
            duration_ms INTEGER,
            output_summary TEXT,
            session_id TEXT,
            project_context TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_session ON observed_tasks(session_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_time ON observed_tasks(timestamp);
    """)
    conn.commit()
    conn.close()
    log.info(f"Sessions database initialized: {sessions_db}")


# ─── Services Configuration ────────────────────────────────────────────────
SERVICES = {
    "mcp_kb": {
        "cmd": [sys.executable, "-m", "mcp_servers.knowledge_base"],
        "cwd": KB_ROOT,
    },
    "mcp_comp": {
        "cmd": [sys.executable, "-m", "mcp_servers.compression"],
        "cwd": KB_ROOT,
    },
    "lsp": {
        "cmd": [sys.executable, "-m", "lsp_servers.eni_compression"],
        "cwd": KB_ROOT,
    },
    "sync": {
        "cmd": [sys.executable, "-m", "sync.sync_daemon", "--daemon"],
        "cwd": KB_ROOT,
    },
    "evolution": {
        "cmd": [sys.executable, "-m", "evolution.adaptive_compression", "evolve", "--generations", "100"],
        "cwd": KB_ROOT,
    },
}


# ─── HTTP Status Endpoint ──────────────────────────────────────────────────
class StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "services": manager.status()}).encode())
        elif self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            status = {
                "services": manager.status(),
                "kb_root": str(KB_ROOT),
                "uptime": time.time() - start_time,
            }
            self.wfile.write(json.dumps(status, indent=2).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


# ─── Main Daemon ───────────────────────────────────────────────────────────
manager = ServiceManager()
start_time = time.time()
shutdown_event = threading.Event()


def signal_handler(signum, frame):
    log.info(f"Received signal {signum}, shutting down...")
    shutdown_event.set()


def run_daemon():
    global manager

    log.info("=" * 60)
    log.info("ENI Knowledge Base Daemon Starting")
    log.info(f"KB_ROOT: {KB_ROOT}")
    log.info("=" * 60)

    # Initialize databases before starting services
    try:
        init_databases()
    except Exception as e:
        log.error(f"Database initialization failed: {e}")

    # Install signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Start all services
    for name, config in SERVICES.items():
        try:
            manager.start_service(name, **config)
            time.sleep(0.5)  # Stagger starts
        except Exception as e:
            log.error(f"Failed to start {name}: {e}")

    # Start HTTP status server
    httpd = HTTPServer(("127.0.0.1", 8765), StatusHandler)
    http_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    http_thread.start()
    log.info("Status HTTP server on http://127.0.0.1:8765")

    # Periodic health check
    def health_check():
        while not shutdown_event.is_set():
            time.sleep(30)
            for name, proc in manager.processes.items():
                if proc.poll() is not None:
                    log.warning(f"Service {name} died (exit={proc.returncode}), restarting...")
                    config = SERVICES.get(name)
                    if config:
                        manager.start_service(name, **config)

    health_thread = threading.Thread(target=health_check, daemon=True)
    health_thread.start()

    # Wait for shutdown
    shutdown_event.wait()

    log.info("Shutting down services...")
    manager.stop_all()
    httpd.shutdown()
    log.info("ENI Knowledge Base Daemon stopped")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ENI KB Daemon")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    parser.add_argument("--status", action="store_true", help="Print status and exit")
    parser.add_argument("--restart", action="store_true", help="Restart all services")
    args = parser.parse_args()

    if args.status:
        m = ServiceManager()
        # Just check existing processes
        import psutil
        for name, config in SERVICES.items():
            found = False
            for proc in psutil.process_iter(['pid', 'cmdline']):
                if config["cmd"][0] in " ".join(proc.info['cmdline'] or []):
                    print(f"  {name}: RUNNING (pid={proc.info['pid']})")
                    found = True
                    break
            if not found:
                print(f"  {name}: STOPPED")
        return

    if args.daemon or len(sys.argv) == 1:
        run_daemon()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()