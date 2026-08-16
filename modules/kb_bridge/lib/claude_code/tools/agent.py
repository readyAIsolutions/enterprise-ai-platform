#!/usr/bin/env python3
"""
AgentTool — Sub-agent Spawning
===============================
Spawn and manage sub-agents for parallel task execution.
Mirrors: src/tools/AgentTool/AgentTool.ts
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from lib.claude_code.tool import (
    Tool,
    ToolResult,
    ToolUseContext,
    ToolProgressData,
    CanUseToolFn,
    ToolProgress,
)

# Import these lazily to avoid circular imports
def _get_default_tools():
    from lib.claude_code.tools import get_default_tools
    return get_default_tools()

def _get_commands():
    from lib.claude_code.command import create_builtin_commands
    return create_builtin_commands()

def _get_default_config():
    from lib.claude_code import create_default_config
    return create_default_config()

def _get_query_engine():
    from lib.claude_code.query_engine import QueryEngine
    return QueryEngine

def _get_app_state():
    from lib.claude_code.state import get_app_state
    return get_app_state

def _set_app_state():
    from lib.claude_code.state import set_app_state
    return set_app_state

def _get_default_can_use_tool():
    from lib.claude_code.permission import default_can_use_tool
    return default_can_use_tool


# ─── Agent Storage ────────────────────────────────────────────────────────────

AGENT_DIR = Path.home() / ".claude_code" / "agents"
AGENT_DIR.mkdir(parents=True, exist_ok=True)


def _get_agent_file(agent_id: str) -> Path:
    return AGENT_DIR / f"{agent_id}.json"


def _save_agent(agent: dict[str, Any]) -> None:
    _get_agent_file(agent["id"]).write_text(json.dumps(agent, indent=2, default=str))


def _load_agent(agent_id: str) -> dict[str, Any] | None:
    f = _get_agent_file(agent_id)
    if f.exists():
        return json.loads(f.read_text())
    return None


# ─── AgentTool ────────────────────────────────────────────────────────────────

class AgentInput(BaseModel):
    task: str = Field(..., description="Task description for the sub-agent")
    agent_type: str = Field(default="general", description="Type: general, coder, researcher, reviewer")
    model: str | None = Field(default=None, description="Model override")
    max_turns: int = Field(default=10, description="Maximum conversation turns")
    tools: list[str] | None = Field(default=None, description="Specific tools to enable")
    context: str | None = Field(default=None, description="Additional context")


class AgentOutput(BaseModel):
    agent_id: str
    status: str
    result: str | None
    turns: int
    duration_ms: int


class AgentProgress(ToolProgressData):
    agent_id: str | None = None
    status: str = "running"
    turn: int = 0


class AgentTool(Tool[AgentInput, AgentOutput, AgentProgress]):
    name = "agent"
    aliases = ["spawn_agent", "subagent"]
    search_hint = "Spawn a sub-agent to handle a task independently"
    input_schema = AgentInput
    output_schema = AgentOutput
    progress_schema = AgentProgress

    def is_enabled(self) -> bool:
        return True

    def is_destructive(self, input: AgentInput) -> bool:
        return False

    async def call(
        self,
        args: AgentInput,
        context: ToolUseContext,
        can_use_tool: CanUseToolFn,
        parent_message: Any,
        on_progress: Any = None,
    ) -> ToolResult[AgentOutput]:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        start_time = datetime.now()

        # Create agent record
        agent = {
            "id": agent_id,
            "task": args.task,
            "agent_type": args.agent_type,
            "model": args.model,
            "max_turns": args.max_turns,
            "tools": args.tools,
            "context": args.context,
            "status": "running",
            "created_at": start_time.isoformat(),
            "completed_at": None,
            "result": None,
            "turns": 0,
        }
        _save_agent(agent)

        # Send progress
        if on_progress:
            on_progress(ToolProgress(
                tool_use_id=agent_id,
                data=AgentProgress(agent_id=agent_id, status="initializing", turn=0)
            ))

        try:
            # Create sub-agent QueryEngine
            config = _get_default_config()
            if args.tools:
                config.tools = [t for t in _get_default_tools() if t.name in args.tools]
            else:
                config.tools = _get_default_tools()
            config.commands = _get_commands()
            config.can_use_tool = _get_default_can_use_tool()
            config.get_app_state = _get_app_state()
            config.set_app_state = _set_app_state()
            config.max_turns = args.max_turns
            config.max_budget_usd = 0.50  # Limit sub-agent cost

            QueryEngine = _get_query_engine()
            engine = QueryEngine(config)

            # Build prompt with context
            prompt = f"""You are a {args.agent_type} sub-agent.
Task: {args.task}
"""
            if args.context:
                prompt += f"\nContext: {args.context}\n"
            prompt += "\nComplete this task and provide a clear result."

            # Run sub-agent
            result_text = ""
            turns = 0
            async for msg in engine.submit_message(prompt):
                turns += 1
                if msg.type == "result":
                    result_text = msg.result or ""
                    break
                elif msg.type == "assistant":
                    # Update progress
                    if on_progress:
                        on_progress(ToolProgress(
                            tool_use_id=agent_id,
                            data=AgentProgress(agent_id=agent_id, status="running", turn=turns)
                        ))

            # Update agent record
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            agent.update({
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
                "result": result_text,
                "turns": turns,
                "duration_ms": duration_ms,
            })
            _save_agent(agent)

            if on_progress:
                on_progress(ToolProgress(
                    tool_use_id=agent_id,
                    data=AgentProgress(agent_id=agent_id, status="completed", turn=turns)
                ))

            return ToolResult(
                data=AgentOutput(
                    agent_id=agent_id,
                    status="completed",
                    result=result_text,
                    turns=turns,
                    duration_ms=duration_ms,
                )
            )

        except Exception as e:
            agent.update({
                "status": "failed",
                "completed_at": datetime.now().isoformat(),
                "result": f"Error: {str(e)}",
            })
            _save_agent(agent)
            raise


# ─── Exports ─────────────────────────────────────────────────────────────────

agent_tool = AgentTool()

__all__ = ["AgentTool", "AgentInput", "AgentOutput", "AgentProgress", "agent_tool"]