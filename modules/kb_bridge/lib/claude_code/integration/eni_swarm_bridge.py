#!/usr/bin/env python3
"""
ENI Swarm ↔ Claude Code Integration
====================================
Bridge between ENI Swarm Master Driver and QueryEngine.
Allows ENI minis to use full Claude Code tool system.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

# Lazy imports to avoid circular dependency
def _get_query_engine():
    from lib.claude_code.query_engine import QueryEngine
    return QueryEngine

def _get_query_engine_config():
    from lib.claude_code.query_engine import QueryEngineConfig
    return QueryEngineConfig

def _get_default_config():
    from lib.claude_code import create_default_config
    return create_default_config

def _get_default_tools():
    from lib.claude_code.tools import get_default_tools
    return get_default_tools

def _get_commands():
    from lib.claude_code.command import create_builtin_commands
    return create_builtin_commands

def _get_default_can_use_tool():
    from lib.claude_code.permission import default_can_use_tool
    return default_can_use_tool

def _get_app_state():
    from lib.claude_code.state import get_app_state
    return get_app_state

def _set_app_state():
    from lib.claude_code.state import set_app_state
    return set_app_state

def _get_tool_use_context():
    from lib.claude_code.tool import ToolUseContext
    return ToolUseContext


# ─── ENI Mini Agent ─────────────────────────────────────────────────────────


class ENIMiniAgent:
    """
    ENI Mini Agent powered by Claude Code QueryEngine.
    Each mini runs a QueryEngine instance with full tool access.
    """

    def __init__(
        self,
        name: str,
        workdir: str,
        model: str = "free-router",
        max_turns: int = 10,
        max_budget: float = 1.0,
    ):
        self.name = name
        self.workdir = Path(workdir).expanduser().resolve()
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.model = model
        self.max_turns = max_turns
        self.max_budget = max_budget

        # State
        self.status_file = self.workdir / f"STATUS_{name}.md"
        self.fifo_path = Path(f"/tmp/eni_ctl_{name}")
        self.engine: Any | None = None
        self.running = False
        self.current_task: str | None = None

        # Ensure FIFO exists
        self._ensure_fifo()

    def _ensure_fifo(self):
        try:
            if self.fifo_path.exists() and not self.fifo_path.is_fifo():
                self.fifo_path.unlink()
            if not self.fifo_path.exists():
                os.mkfifo(self.fifo_path, 0o666)
        except Exception:
            pass

    async def initialize(self):
        """Initialize the QueryEngine."""
        config = _get_default_config()()
        config.cwd = str(self.workdir)
        config.tools = _get_default_tools()()
        config.commands = _get_commands()()
        config.can_use_tool = _get_default_can_use_tool()
        config.get_app_state = _get_app_state()
        config.set_app_state = _set_app_state()
        config.max_turns = self.max_turns
        config.max_budget_usd = self.max_budget
        config.user_specified_model = self.model

        QueryEngine = _get_query_engine()
        self.engine = QueryEngine(config)

    async def execute_task(self, task: str) -> str:
        """Execute a single task and return result."""
        if not self.engine:
            await self.initialize()

        self.current_task = task
        self._write_status("IN-PROGRESS", f"Starting task: {task[:50]}")

        result_text = ""
        try:
            async for msg in self.engine.submit_message(task):
                if msg.type == "result":
                    result_text = msg.result or ""
                    if msg.is_error:
                        self._write_status("BLOCKED", f"Error: {result_text}")
                    else:
                        self._write_status("DONE", f"Completed: {result_text[:50]}")
                    break
                elif msg.type == "assistant":
                    # Progress update
                    self._write_status("IN-PROGRESS", f"Working... turn {msg.num_turns if hasattr(msg, 'num_turns') else 0}")

        except Exception as e:
            result_text = f"Error: {e}"
            self._write_status("BLOCKED", f"Exception: {e}")

        self.current_task = None
        return result_text

    def _write_status(self, state: str, detail: str):
        """Write STATUS file."""
        content = f"""[{state}] {detail}
verified={detail}
blocker=
next=awaiting next task
"""
        self.status_file.write_text(content)

    async def listen_fifo(self):
        """Listen for tasks via FIFO."""
        if not self.fifo_path.exists():
            return

        try:
            # Non-blocking read
            import select
            fd = os.open(self.fifo_path, os.O_RDONLY | os.O_NONBLOCK)
            try:
                ready, _, _ = select.select([fd], [], [], 0.1)
                if ready:
                    data = os.read(fd, 4096)
                    if data:
                        task = data.decode().strip()
                        if task and len(task) > 10:
                            await self.execute_task(task)
            finally:
                os.close(fd)
        except Exception:
            pass

    async def run_loop(self, interval: float = 5.0):
        """Main loop: execute tasks from FIFO."""
        self.running = True
        while self.running:
            await self.listen_fifo()
            await asyncio.sleep(interval)

    def stop(self):
        self.running = False


# ─── ENI Swarm Master Integration ───────────────────────────────────────────


class ENISwarmMaster:
    """
    ENI Swarm Master that manages minis via QueryEngine.
    Replaces hermes run with QueryEngine-based execution.
    """

    def __init__(
        self,
        project: str = "ENI_Swarm_NEW",
        max_concurrent: int = 6,
        model: str = "free-router",
    ):
        self.project = project
        self.max_concurrent = max_concurrent
        self.model = model
        self.minis: dict[str, ENIMiniAgent] = {}
        self.running = False
        self.semaphore = asyncio.Semaphore(max_concurrent)

    def add_mini(
        self,
        name: str,
        workdir: str,
        task: str = "",
        max_turns: int = 10,
        max_budget: float = 1.0,
    ) -> ENIMiniAgent:
        """Add a mini agent to the swarm."""
        mini = ENIMiniAgent(
            name=name,
            workdir=workdir,
            model=self.model,
            max_turns=max_turns,
            max_budget=max_budget,
        )
        self.minis[name] = mini
        return mini

    def load_task_roster(self, config_path: Path) -> list[dict[str, Any]]:
        """Load task roster from JSON config."""
        import json
        if not config_path.exists():
            return []
        data = json.loads(config_path.read_text())
        return data.get("tasks", [])

    async def start_all(self, config_dir: Path = Path("~/Desktop/Projects/ENI_Swarm_NEW/config").expanduser()):
        """Start all minis from task roster."""
        # Load build tasks
        build_tasks = self.load_task_roster(config_dir / "eni_build_tasks.json")
        herself_tasks = self.load_task_roster(config_dir / "eni_herself_tasks.json")

        all_tasks = build_tasks + herself_tasks

        for task_config in all_tasks:
            name = task_config["name"]
            if name == "MASTER":
                continue

            workdir = task_config.get("workdir", "~/Desktop/Projects/ENI_Swarm_NEW")
            task_prompt = task_config.get("task", "")
            model = task_config.get("model", self.model)

            self.add_mini(
                name=name,
                workdir=workdir,
                task=task_prompt,
                max_turns=10,
                max_budget=1.0,
            )

        # Initialize all
        for mini in self.minis.values():
            await mini.initialize()

    async def run_cycle(self):
        """Run one coordination cycle."""
        # Check FIFOs for new tasks
        for mini in self.minis.values():
            if mini.running and not mini.current_task:
                await mini.listen_fifo()

        # Update master status
        await self._write_master_status()

    async def _write_master_status(self):
        """Write MASTER_STATUS.md."""
        lines = [
            f"# MASTER_STATUS.md — ENI Swarm + Claude Code",
            f"## Cycle {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Model**: {self.model}",
            f"",
            f"| Mini | State | Task | Workdir |",
            f"|------|-------|------|---------|",
        ]

        for name, mini in sorted(self.minis.items()):
            state = "RUNNING" if mini.running else "STOPPED"
            if mini.current_task:
                state = "EXECUTING"
            task_preview = (mini.current_task[:50] + "...") if mini.current_task else "idle"
            lines.append(f"| {name} | {state} | {task_preview} | {mini.workdir} |")

        status_file = Path("~/Desktop/Projects/ENI_Swarm_NEW/tasks/status/MASTER_STATUS.md").expanduser()
        status_file.parent.mkdir(parents=True, exist_ok=True)
        status_file.write_text("\n".join(lines))

    async def run_loop(self, interval: float = 30.0):
        """Main coordination loop."""
        self.running = True
        while self.running:
            await self.run_cycle()
            await asyncio.sleep(interval)

    def stop(self):
        self.running = False
        for mini in self.minis.values():
            mini.stop()


# ─── Integration with ENI Master Driver ─────────────────────────────────────


async def execute_with_queryengine(
    mini_name: str,
    task_prompt: str,
    workdir: str,
    model: str = "free-router",
    max_turns: int = 10,
    max_budget: float = 1.0,
) -> str:
    """
    Execute a task using QueryEngine instead of `hermes run`.
    This is the core integration point.
    """
    config = _get_default_config()()
    config.cwd = workdir
    config.tools = _get_default_tools()()
    config.commands = _get_commands()()
    config.can_use_tool = _get_default_can_use_tool()
    config.get_app_state = _get_app_state()
    config.set_app_state = _set_app_state()
    config.max_turns = max_turns
    config.max_budget_usd = max_budget
    config.user_specified_model = model

    QueryEngine = _get_query_engine()
    engine = QueryEngine(config)

    result_text = ""
    async for msg in engine.submit_message(task_prompt):
        if msg.type == "result":
            result_text = msg.result or ""
            break

    return result_text


# ─── CLI ────────────────────────────────────────────────────────────────────


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="ENI Swarm + Claude Code Integration")
    parser.add_argument("--config-dir", type=Path, default=Path("~/Desktop/Projects/ENI_Swarm_NEW/config").expanduser())
    parser.add_argument("--project", default="ENI_Swarm_NEW")
    parser.add_argument("--model", default="free-router")
    parser.add_argument("--max-concurrent", type=int, default=6)
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--single-cycle", action="store_true")
    args = parser.parse_args()

    master = ENISwarmMaster(
        project=args.project,
        max_concurrent=args.max_concurrent,
        model=args.model,
    )

    await master.start_all(args.config_dir)

    if args.single_cycle:
        await master.run_cycle()
    else:
        await master.run_loop(args.interval)


if __name__ == "__main__":
    asyncio.run(main())