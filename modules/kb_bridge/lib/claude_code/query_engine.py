#!/usr/bin/env python3
"""
Claude Code QueryEngine — Python Port
======================================
Core LLM orchestration with tool loops, cost tracking, permission handling.
Mirrors: src/QueryEngine.ts, src/query.ts
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field

from lib.claude_code.tool import (
    Tool,
    ToolUseContext,
    ToolResult,
    Tools,
    CanUseToolFn,
    PermissionResult,
    PermissionMode,
    ToolPermissionContext,
    tool_matches_name,
)
from lib.claude_code.command import Command, get_command_registry


# ─── Type Definitions ────────────────────────────────────────────────────────


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class MessageContent(BaseModel):
    """Content block in a message."""
    type: str  # text, tool_use, tool_result, thinking
    text: str | None = None
    tool_use_id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None
    output: str | None = None
    is_error: bool = False


class Message(BaseModel):
    """Conversation message."""
    role: MessageRole
    content: list[MessageContent] | str
    timestamp: datetime = Field(default_factory=datetime.now)
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_uuid: str | None = None
    is_meta: bool = False
    is_visible_in_transcript_only: bool = False


class SDKMessage(BaseModel):
    """Message for SDK output."""
    type: str
    message: dict[str, Any] | None = None
    session_id: str | None = None
    parent_tool_use_id: str | None = None
    uuid: str | None = None
    timestamp: datetime | None = None
    is_replay: bool = False
    is_synthetic: bool = False
    subtype: str | None = None
    duration_ms: int | None = None
    duration_api_ms: int | None = None
    num_turns: int | None = None
    result: str | None = None
    stop_reason: str | None = None
    total_cost_usd: float | None = None
    usage: dict[str, int] | None = None
    model_usage: dict[str, Any] | None = None
    permission_denials: list[dict[str, Any]] | None = None
    fast_mode_state: str | None = None
    structured_output: Any | None = None


class SDKStatus(str, Enum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    READY = "ready"
    ERROR = "error"


@dataclass
class QueryEngineConfig:
    """Configuration for QueryEngine."""
    cwd: str
    tools: Tools
    commands: list[Command]
    can_use_tool: CanUseToolFn
    get_app_state: Callable[[], Any]
    set_app_state: Callable[[Callable[[Any], Any]], None]
    initial_messages: list[Message] = field(default_factory=list)
    custom_system_prompt: str | None = None
    append_system_prompt: str | None = None
    user_specified_model: str | None = None
    fallback_model: str | None = None
    max_turns: int | None = None
    max_budget_usd: float | None = None
    verbose: bool = False
    abort_controller: asyncio.Event | None = None


class Usage(BaseModel):
    """Token usage tracking."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    def total(self) -> int:
        return self.input_tokens + self.output_tokens


EMPTY_USAGE = Usage()


# ─── QueryEngine ─────────────────────────────────────────────────────────────


class QueryEngine:
    """
    Core query engine that manages the conversation lifecycle.
    Handles tool loops, permissions, cost tracking, and message normalization.
    """

    def __init__(self, config: QueryEngineConfig):
        self.config = config
        self.messages: list[Message] = config.initial_messages.copy()
        self.abort_controller = config.abort_controller or asyncio.Event()
        self.permission_denials: list[dict[str, Any]] = []
        self.total_usage = EMPTY_USAGE
        self.turn_count = 0
        self.last_stop_reason: str | None = None
        self.structured_output: Any = None
        self.session_id = str(uuid.uuid4())
        self.start_time = time.time()

    async def submit_message(
        self,
        prompt: str | list[dict[str, Any]],
        options: dict[str, Any] | None = None,
    ) -> AsyncGenerator[SDKMessage, None]:
        """
        Submit a message and process the conversation turn.
        Yields SDK messages for each step.
        """
        options = options or {}

        # Prepare context
        context = self._build_tool_use_context()

        # Add user message
        user_msg = self._create_user_message(prompt)
        self.messages.append(user_msg)

        # Yield user message replay if requested
        if options.get("replay_user_messages", False):
            yield self._to_sdk_user_message(user_msg)

        # Main conversation loop
        while not self.abort_controller.is_set():
            # Check turn limit
            if self.config.max_turns and self.turn_count >= self.config.max_turns:
                yield self._create_result_message(
                    "error_max_turns",
                    f"Reached maximum turns ({self.config.max_turns})",
                    is_error=True,
                )
                return

            # Check budget
            if self.config.max_budget_usd:
                cost = self._calculate_cost()
                if cost >= self.config.max_budget_usd:
                    yield self._create_result_message(
                        "error_max_budget_usd",
                        f"Reached maximum budget (${self.config.max_budget_usd})",
                        is_error=True,
                    )
                    return

            # Build system prompt
            system_prompt = self._build_system_prompt()

            # Get available tools
            tools = self._get_available_tools()

            # Call the model (placeholder - integrate with actual API)
            response = await self._call_model(
                system_prompt=system_prompt,
                messages=self.messages,
                tools=tools,
            )

            # Process response
            assistant_msg = self._create_assistant_message(response)
            self.messages.append(assistant_msg)

            # Yield assistant message
            yield self._to_sdk_assistant_message(assistant_msg)

            # Handle tool uses
            tool_uses = self._extract_tool_uses(response)
            if tool_uses:
                # Execute tools
                tool_results = await self._execute_tools(tool_uses, context)

                # Add tool results as messages
                for result in tool_results:
                    tool_msg = self._create_tool_result_message(result)
                    self.messages.append(tool_msg)
                    yield self._to_sdk_tool_result_message(tool_msg)

                self.turn_count += 1
                continue

            # No tool uses - conversation turn complete
            self.turn_count += 1

            # Check stop reason
            stop_reason = self._get_stop_reason(response)
            self.last_stop_reason = stop_reason

            if stop_reason == "end_turn":
                # Normal completion
                result_text = self._extract_text_response(response)
                yield self._create_result_message("success", result_text)
                return
            elif stop_reason == "max_tokens":
                yield self._create_result_message(
                    "error_max_tokens",
                    "Response truncated due to token limit",
                    is_error=True,
                )
                return
            else:
                # Continue loop for other stop reasons
                continue

        # Aborted
        yield self._create_result_message(
            "error_aborted",
            "Conversation aborted",
            is_error=True,
        )

    def _build_tool_use_context(self) -> ToolUseContext:
        """Build the tool use context."""
        return ToolUseContext(
            options={
                "commands": self.config.commands,
                "debug": self.config.verbose,
                "tools": self.config.tools,
                "verbose": self.config.verbose,
                "mainLoopModel": self.config.user_specified_model or "default",
                "thinkingConfig": {"type": "disabled"},
                "mcpClients": [],
                "mcpResources": {},
                "isNonInteractiveSession": True,
                "agentDefinitions": {"activeAgents": [], "allAgents": []},
                "maxBudgetUsd": self.config.max_budget_usd,
            },
            abort_controller=self.abort_controller,
            read_file_state=None,
            get_app_state=self.config.get_app_state,
            set_app_state=self.config.set_app_state,
            messages=self.messages,
        )

    def _build_system_prompt(self) -> str:
        """Build the system prompt."""
        parts = []

        if self.config.custom_system_prompt:
            parts.append(self.config.custom_system_prompt)

        # Add tool descriptions
        tool_descs = []
        for tool in self.config.tools:
            if tool.is_enabled():
                tool_descs.append(f"- {tool.name}: {tool.search_hint}")
        if tool_descs:
            parts.append("Available tools:\n" + "\n".join(tool_descs))

        if self.config.append_system_prompt:
            parts.append(self.config.append_system_prompt)

        return "\n\n".join(parts)

    def _get_available_tools(self) -> Tools:
        """Get tools that are currently available."""
        return [t for t in self.config.tools if t.is_enabled()]

    async def _call_model(
        self,
        system_prompt: str,
        messages: list[Message],
        tools: Tools,
    ) -> dict[str, Any]:
        """
        Call the LLM API.
        This is a placeholder - integrate with actual API (Anthropic, OpenRouter, etc.)
        """
        # Simulate API response
        # In production, call Anthropic API or OpenRouter
        await asyncio.sleep(0.1)  # Simulate network latency

        return {
            "content": [
                {"type": "text", "text": "I'll help you with that."}
            ],
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
            },
        }

    def _create_user_message(self, prompt: str | list[dict[str, Any]]) -> Message:
        """Create a user message from prompt."""
        if isinstance(prompt, str):
            content = [MessageContent(type="text", text=prompt)]
        else:
            content = [
                MessageContent(type="text", text=block.get("text", ""))
                for block in prompt
            ]
        return Message(
            role=MessageRole.USER,
            content=content,
        )

    def _create_assistant_message(self, response: dict[str, Any]) -> Message:
        """Create assistant message from API response."""
        content = []
        for block in response.get("content", []):
            if block["type"] == "text":
                content.append(MessageContent(type="text", text=block["text"]))
            elif block["type"] == "tool_use":
                content.append(MessageContent(
                    type="tool_use",
                    tool_use_id=block["id"],
                    name=block["name"],
                    input=block["input"],
                ))
        return Message(
            role=MessageRole.ASSISTANT,
            content=content,
        )

    def _extract_tool_uses(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract tool uses from response."""
        tool_uses = []
        for block in response.get("content", []):
            if block["type"] == "tool_use":
                tool_uses.append(block)
        return tool_uses

    async def _execute_tools(
        self,
        tool_uses: list[dict[str, Any]],
        context: ToolUseContext,
    ) -> list[ToolResult]:
        """Execute multiple tools in parallel."""
        tasks = []
        for tool_use in tool_uses:
            tool = self._find_tool(tool_use["name"])
            if not tool:
                continue

            # Create task
            task = self._execute_single_tool(tool, tool_use, context)
            tasks.append(task)

        # Run in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter exceptions
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                tool_use = tool_uses[i]
                valid_results.append(ToolResult(
                    data={"error": str(result)},
                    new_messages=[],
                ))
            else:
                valid_results.append(result)

        return valid_results

    async def _execute_single_tool(
        self,
        tool: Tool,
        tool_use: dict[str, Any],
        context: ToolUseContext,
    ) -> ToolResult:
        """Execute a single tool."""
        tool_use_id = tool_use["id"]
        tool_input = tool_use["input"]

        # Validate input against schema
        try:
            validated_input = tool.input_schema(**tool_input)
        except Exception as e:
            return ToolResult(
                data={"error": f"Invalid input: {e}"},
                new_messages=[],
            )

        # Check permissions
        perm_result = await tool.check_permissions(validated_input, context)
        if perm_result.behavior != "allow":
            return ToolResult(
                data={"error": f"Permission denied: {perm_result.reason}"},
                new_messages=[],
            )

        # Execute tool
        try:
            result = await tool.call(
                validated_input,
                context,
                self.config.can_use_tool,
                None,  # parent_message
                None,  # on_progress
            )
            return result
        except Exception as e:
            return ToolResult(
                data={"error": f"Tool execution failed: {e}"},
                new_messages=[],
            )

    def _find_tool(self, name: str) -> Tool | None:
        """Find a tool by name."""
        for tool in self.config.tools:
            if tool_matches_name(tool, name):
                return tool
        return None

    def _create_tool_result_message(self, result: ToolResult) -> Message:
        """Create a tool result message."""
        return Message(
            role=MessageRole.TOOL,
            content=[MessageContent(
                type="tool_result",
                tool_use_id="",
                output=json.dumps(result.data, default=str),
            )],
        )

    def _get_stop_reason(self, response: dict[str, Any]) -> str:
        """Extract stop reason from response."""
        return response.get("stop_reason", "end_turn")

    def _extract_text_response(self, response: dict[str, Any]) -> str:
        """Extract text content from response."""
        texts = []
        for block in response.get("content", []):
            if block["type"] == "text":
                texts.append(block["text"])
        return "\n".join(texts)

    def _calculate_cost(self) -> float:
        """Calculate total cost in USD."""
        # Rough estimate: $3/1M input, $15/1M output (Claude 3.5 Sonnet pricing)
        input_cost = self.total_usage.input_tokens * 3 / 1_000_000
        output_cost = self.total_usage.output_tokens * 15 / 1_000_000
        return input_cost + output_cost

    def _to_sdk_user_message(self, msg: Message) -> SDKMessage:
        """Convert to SDK user message."""
        return SDKMessage(
            type="user",
            message={"role": "user", "content": msg.content},
            session_id=self.session_id,
            uuid=msg.uuid,
            timestamp=msg.timestamp,
        )

    def _to_sdk_assistant_message(self, msg: Message) -> SDKMessage:
        """Convert to SDK assistant message."""
        content = []
        for block in msg.content:
            if block.type == "text":
                content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content.append({
                    "type": "tool_use",
                    "id": block.tool_use_id,
                    "name": block.name,
                    "input": block.input,
                })
        return SDKMessage(
            type="assistant",
            message={"role": "assistant", "content": content},
            session_id=self.session_id,
            uuid=msg.uuid,
            timestamp=msg.timestamp,
        )

    def _to_sdk_tool_result_message(self, msg: Message) -> SDKMessage:
        """Convert to SDK tool result message."""
        return SDKMessage(
            type="user",
            message={"role": "user", "content": msg.content},
            session_id=self.session_id,
            uuid=msg.uuid,
            timestamp=msg.timestamp,
        )

    def _create_result_message(
        self,
        subtype: str,
        result: str,
        is_error: bool = False,
    ) -> SDKMessage:
        """Create final result message."""
        duration_ms = int((time.time() - self.start_time) * 1000)
        cost = self._calculate_cost()

        return SDKMessage(
            type="result",
            subtype=subtype,
            is_error=is_error,
            duration_ms=duration_ms,
            duration_api_ms=0,
            num_turns=self.turn_count,
            result=result,
            stop_reason=self.last_stop_reason,
            session_id=self.session_id,
            total_cost_usd=cost,
            usage=self.total_usage.model_dump(),
            model_usage={},
            permission_denials=self.permission_denials,
            uuid=str(uuid.uuid4()),
        )

    def interrupt(self) -> None:
        """Interrupt the current query."""
        self.abort_controller.set()

    def get_messages(self) -> list[Message]:
        """Get current conversation messages."""
        return self.messages.copy()


# ─── Factory Function ────────────────────────────────────────────────────────


async def ask(
    prompt: str,
    config: QueryEngineConfig,
) -> AsyncGenerator[SDKMessage, None]:
    """
    Convenience function for one-shot queries.
    """
    engine = QueryEngine(config)
    async for msg in engine.submit_message(prompt):
        yield msg


# ─── Export ──────────────────────────────────────────────────────────────────

__all__ = [
    "QueryEngine",
    "QueryEngineConfig",
    "Message",
    "MessageRole",
    "MessageContent",
    "SDKMessage",
    "SDKStatus",
    "Usage",
    "EMPTY_USAGE",
    "ask",
]