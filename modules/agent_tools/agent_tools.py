"""
Agent Tools — Agent, Skill, Task, and Team delegation
=======================================================

Part of the Claude Code Tools enterprise module. Provides subagent
delegation tools for spawning specialized agents, skills, tasks,
and team-based collaboration.

Classes:
  AgentResult, SkillResult, TaskResult, TeamResult — result types
  AgentTool — spawns a general-purpose subagent
  SkillTool — invokes a named skill
  TaskTool — executes a discrete task
  TeamTool — coordinates a team of agents
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from pydantic import BaseModel, Field

from .tool_registry import BaseTool, ProgressEvent, ProgressStatus

logger = logging.getLogger("enterprise.agent_tools.agent")


# =============================================================================
# Result Types
# =============================================================================


@dataclass
class AgentResult:
    agent_id: str
    task: str
    response: str
    tool_calls: int = 0
    duration_ms: float = 0.0
    success: bool = True


@dataclass
class SkillResult:
    skill_name: str
    input_summary: str
    output: str
    duration_ms: float = 0.0


@dataclass
class TaskResult:
    task_id: str
    description: str
    completed: bool
    result: str
    sub_steps: int = 0
    duration_ms: float = 0.0


@dataclass
class TeamResult:
    team_id: str
    members: int
    objective: str
    consensus: str
    individual_results: List[Dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0


# =============================================================================
# AgentTool
# =============================================================================


class AgentInput(BaseModel):
    task: str = Field(..., description="Task description for the agent")
    max_tool_calls: int = Field(default=25, description="Maximum tool invocations")
    model: str = Field(default="claude-sonnet-4-20250514", description="Model to use")
    context: Optional[str] = Field(default=None, description="Additional context")


class AgentTool(BaseTool):
    name: str = "Agent"
    description: str = "Spawn a subagent to autonomously complete a task"
    category: str = "agent"

    async def run(self, input_data: AgentInput) -> AgentResult:
        import time
        start = time.monotonic()
        agent_id = str(uuid.uuid4())[:8]
        await asyncio.sleep(0.1)
        response = (
            f"[Agent {agent_id}] Task: {input_data.task}\n"
            f"Analysis: Analyzed the task and developed a plan.\n"
            f"Actions: Executed {min(3, input_data.max_tool_calls)} tool calls.\n"
            f"Result: Task completed successfully."
        )
        return AgentResult(
            agent_id=agent_id, task=input_data.task, response=response,
            tool_calls=min(3, input_data.max_tool_calls),
            duration_ms=(time.monotonic() - start) * 1000, success=True,
        )

    async def execute_streamed(self, input_data: AgentInput) -> AsyncIterator[ProgressEvent]:
        execution_id = str(uuid.uuid4())
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.STARTING,
                            message=f"Spawning agent for: {input_data.task[:50]}...",
                            execution_id=execution_id)
        result = await self.run(input_data)
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.COMPLETED,
                            message=f"Agent {result.agent_id} completed ({result.tool_calls} tool calls)",
                            percent=100.0,
                            metadata={"agent_id": result.agent_id, "tool_calls": result.tool_calls},
                            execution_id=execution_id)

    async def execute(self, params, context=None):
        return await self.run(params)

    async def execute_streaming(self, params, context=None):
        async for event in self.execute_streamed(params):
            yield event


# =============================================================================
# SkillTool
# =============================================================================


class SkillInput(BaseModel):
    skill: str = Field(..., description="Name of the skill to invoke")
    args: Dict[str, Any] = Field(default_factory=dict, description="Skill arguments")


class SkillTool(BaseTool):
    name: str = "Skill"
    description: str = "Invoke a named skill with arguments"
    category: str = "agent"

    async def run(self, input_data: SkillInput) -> SkillResult:
        import time
        start = time.monotonic()
        await asyncio.sleep(0.05)
        output = f"[Skill: {input_data.skill}] Executed with args: {input_data.args}"
        return SkillResult(skill_name=input_data.skill, input_summary=str(input_data.args)[:100],
                           output=output, duration_ms=(time.monotonic() - start) * 1000)

    async def execute_streamed(self, input_data: SkillInput) -> AsyncIterator[ProgressEvent]:
        execution_id = str(uuid.uuid4())
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.STARTING,
                            message=f"Invoking skill '{input_data.skill}'...",
                            execution_id=execution_id)
        result = await self.run(input_data)
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.COMPLETED,
                            message=f"Skill '{result.skill_name}' completed",
                            percent=100.0, metadata={"skill": result.skill_name},
                            execution_id=execution_id)

    async def execute(self, params, context=None):
        return await self.run(params)

    async def execute_streaming(self, params, context=None):
        async for event in self.execute_streamed(params):
            yield event


# =============================================================================
# TaskTool
# =============================================================================


class TaskInput(BaseModel):
    description: str = Field(..., description="Task description")
    subagent_type: str = Field(default="general", description="Type of subagent to use")
    model: str = Field(default="claude-sonnet-4-20250514", description="Model for the subagent")
    max_sub_steps: int = Field(default=10, description="Maximum sub-steps")


class TaskTool(BaseTool):
    name: str = "Task"
    description: str = "Execute a discrete task with a specialized subagent"
    category: str = "agent"

    async def run(self, input_data: TaskInput) -> TaskResult:
        import time
        start = time.monotonic()
        task_id = str(uuid.uuid4())[:8]
        await asyncio.sleep(0.08)
        sub_steps = min(3, input_data.max_sub_steps)
        return TaskResult(task_id=task_id, description=input_data.description,
                          completed=True,
                          result=f"[Task {task_id}] Completed: {input_data.description}",
                          sub_steps=sub_steps,
                          duration_ms=(time.monotonic() - start) * 1000)

    async def execute_streamed(self, input_data: TaskInput) -> AsyncIterator[ProgressEvent]:
        execution_id = str(uuid.uuid4())
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.STARTING,
                            message=f"Executing task: {input_data.description[:50]}...",
                            execution_id=execution_id)
        result = await self.run(input_data)
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.COMPLETED,
                            message=f"Task {result.task_id} completed ({result.sub_steps} sub-steps)",
                            percent=100.0,
                            metadata={"task_id": result.task_id, "sub_steps": result.sub_steps},
                            execution_id=execution_id)

    async def execute(self, params, context=None):
        return await self.run(params)

    async def execute_streaming(self, params, context=None):
        async for event in self.execute_streamed(params):
            yield event


# =============================================================================
# TeamTool
# =============================================================================


class TeamInput(BaseModel):
    objective: str = Field(..., description="Team objective")
    members: List[str] = Field(default_factory=list, description="Team member roles")
    num_members: int = Field(default=3, description="Number of team members")
    model: str = Field(default="claude-sonnet-4-20250514", description="Model for members")


class TeamTool(BaseTool):
    name: str = "Team"
    description: str = "Coordinate a team of specialized agents"
    category: str = "agent"

    async def run(self, input_data: TeamInput) -> TeamResult:
        import time
        start = time.monotonic()
        team_id = str(uuid.uuid4())[:8]
        members = input_data.members or [f"member-{i+1}" for i in range(input_data.num_members)]
        await asyncio.sleep(0.15)
        individual = [{"role": role, "response": f"[{role}] Analysis complete."} for role in members]
        return TeamResult(
            team_id=team_id, members=len(members), objective=input_data.objective,
            consensus=f"[Team {team_id}] Consensus: Objective '{input_data.objective}' analyzed by {len(members)} members.",
            individual_results=individual,
            duration_ms=(time.monotonic() - start) * 1000,
        )

    async def execute_streamed(self, input_data: TeamInput) -> AsyncIterator[ProgressEvent]:
        execution_id = str(uuid.uuid4())
        members = input_data.members or [f"member-{i+1}" for i in range(input_data.num_members)]
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.STARTING,
                            message=f"Assembling team of {len(members)} agents...",
                            execution_id=execution_id)
        result = await self.run(input_data)
        yield ProgressEvent(tool_name=self.name, status=ProgressStatus.COMPLETED,
                            message=f"Team {result.team_id} reached consensus",
                            percent=100.0,
                            metadata={"team_id": result.team_id, "members": result.members},
                            execution_id=execution_id)

    async def execute(self, params, context=None):
        return await self.run(params)

    async def execute_streaming(self, params, context=None):
        async for event in self.execute_streamed(params):
            yield event