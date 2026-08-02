"""
BuddySystem — Shared-Context Agent Teammates
=============================================

Part of the Claude Code Infra enterprise module. Provides collaborative
agent "buddies" that share context and work together on tasks.

Classes:
  BuddyRole — role enum for buddy agents
  SharedContext — shared context between buddies
  BuddyAgent — an individual buddy with role and context
  BuddyManager — orchestrates buddy teams
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional

logger = logging.getLogger("enterprise.agent_infra.buddy")

try:
    from enterprise.platform_kernel import EventBus, Event, HealthStatus
except ImportError:
    from platform_kernel import EventBus, Event, HealthStatus


# =============================================================================
# Enums
# =============================================================================


class BuddyRole(Enum):
    """Roles that buddies can assume in a team."""
    ARCHITECT = "architect"
    DEVELOPER = "developer"
    REVIEWER = "reviewer"
    TESTER = "tester"
    DOCUMENTER = "documenter"
    DEVOPS = "devops"
    ANALYST = "analyst"
    CUSTOM = "custom"


class BuddyState(Enum):
    """State of a buddy agent."""
    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting"
    COMPLETED = "completed"
    ERROR = "error"


# =============================================================================
# SharedContext
# =============================================================================


@dataclass
class SharedContext:
    """Shared context between buddy agents.

    Contains the common knowledge, task description, conversation history,
    and artifacts that all buddies on a team can access.

    Attributes:
        context_id: Unique context identifier.
        task: The shared task/objective.
        conversation: Shared conversation history.
        artifacts: Shared files, code, data.
        created_at: When the context was created.
        updated_at: Last update timestamp.
    """
    context_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task: str = ""
    conversation: List[Dict[str, str]] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_message(self, sender: str, message: str) -> None:
        """Add a message to the shared conversation."""
        self.conversation.append({
            "sender": sender,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.updated_at = datetime.now(timezone.utc)

    def add_artifact(self, key: str, value: Any) -> None:
        """Share an artifact (file, code, data)."""
        self.artifacts[key] = value
        self.updated_at = datetime.now(timezone.utc)

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the shared context."""
        return {
            "context_id": self.context_id,
            "task": self.task,
            "message_count": len(self.conversation),
            "artifact_count": len(self.artifacts),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# =============================================================================
# BuddyAgent
# =============================================================================


@dataclass
class BuddyAgent:
    """An individual buddy agent with a role and shared context.

    Each buddy has a specific role, can execute tasks within that role,
    and communicates through the shared context.

    Attributes:
        buddy_id: Unique identifier.
        name: Human-readable name.
        role: The buddy's role in the team.
        context: Reference to the shared context.
        state: Current work state.
        capabilities: List of capabilities.
    """
    buddy_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    role: BuddyRole = BuddyRole.CUSTOM
    context: Optional[SharedContext] = None
    state: BuddyState = BuddyState.IDLE
    capabilities: List[str] = field(default_factory=list)

    async def execute(self, instruction: str) -> str:
        """Execute a task instruction within this buddy's role.

        Args:
            instruction: The task instruction.

        Returns:
            The buddy's response/output.
        """
        self.state = BuddyState.WORKING
        await asyncio.sleep(0.05)  # Simulate work

        response = f"[{self.name}/{self.role.value}] Executed: {instruction}"

        if self.context:
            self.context.add_message(self.name, response)

        self.state = BuddyState.IDLE
        return response

    async def review(self, content: str) -> Dict[str, Any]:
        """Review content and provide feedback.

        Args:
            content: Content to review.

        Returns:
            Review feedback.
        """
        self.state = BuddyState.WORKING
        await asyncio.sleep(0.03)

        feedback = {
            "reviewer": self.name,
            "role": self.role.value,
            "approved": True,
            "comments": [f"[{self.role.value}] Looks good."],
            "suggestions": [],
        }
        self.state = BuddyState.IDLE
        return feedback


# =============================================================================
# BuddyManager
# =============================================================================


class BuddyManager:
    """Orchestrates buddy agent teams with shared context.

    Creates and manages teams of buddy agents that collaborate on tasks.
    Supports spawning buddies with specific roles, managing shared context,
    and coordinating multi-agent workflows.

    Usage::

        mgr = BuddyManager(event_bus=eb)
        await mgr.initialize()
        ctx = mgr.create_context("Build a REST API")
        mgr.spawn_buddy("Alice", BuddyRole.ARCHITECT, ctx)
        mgr.spawn_buddy("Bob", BuddyRole.DEVELOPER, ctx)
        result = await mgr.delegate(ctx.context_id, "Implement GET /users")
        await mgr.shutdown()
    """

    def __init__(self, event_bus: Optional[EventBus] = None,
                 config: Optional[Dict[str, Any]] = None) -> None:
        self._event_bus = event_bus
        self._config = config or {}
        self._contexts: Dict[str, SharedContext] = {}
        self._buddies: Dict[str, BuddyAgent] = {}
        self._max_buddies_per_team: int = self._config.get("max_buddies_per_team", 10)
        self._status = HealthStatus.UNKNOWN

    async def initialize(self) -> None:
        self._status = HealthStatus.HEALTHY
        logger.info("BuddyManager initialized (max_buddies_per_team=%d)",
                     self._max_buddies_per_team)

    async def health_check(self) -> bool:
        return self._status == HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        """Shut down: clear all buddies and contexts."""
        self._buddies.clear()
        self._contexts.clear()
        self._status = HealthStatus.UNKNOWN
        logger.info("BuddyManager shut down")

    def create_context(self, task: str) -> SharedContext:
        """Create a new shared context for a team.

        Args:
            task: Description of the shared task.

        Returns:
            A new SharedContext.
        """
        ctx = SharedContext(task=task)
        self._contexts[ctx.context_id] = ctx
        logger.info("Created shared context %s for task: %s", ctx.context_id, task)
        return ctx

    def get_context(self, context_id: str) -> Optional[SharedContext]:
        """Get a shared context by ID."""
        return self._contexts.get(context_id)

    def spawn_buddy(self, name: str, role: BuddyRole,
                    context: Optional[SharedContext] = None,
                    capabilities: Optional[List[str]] = None) -> BuddyAgent:
        """Spawn a new buddy agent.

        Args:
            name: Human-readable name.
            role: The buddy's role.
            context: Optional shared context to join.
            capabilities: Optional list of capabilities.

        Returns:
            The spawned BuddyAgent.

        Raises:
            ValueError: If the team would exceed max_buddies_per_team.
        """
        if context and context.context_id not in self._contexts:
            self._contexts[context.context_id] = context

        team_size = sum(1 for b in self._buddies.values()
                        if b.context and b.context.context_id == context.context_id) if context else 0
        if team_size >= self._max_buddies_per_team:
            raise ValueError(f"Team at capacity ({self._max_buddies_per_team} buddies max)")

        buddy = BuddyAgent(
            name=name,
            role=role,
            context=context,
            capabilities=capabilities or [],
        )
        self._buddies[buddy.buddy_id] = buddy
        logger.info("Spawned buddy %s (%s) role=%s", buddy.buddy_id, name, role.value)

        self._publish_event("claude.infra.buddy.spawned", {
            "buddy_id": buddy.buddy_id,
            "name": name,
            "role": role.value,
            "context_id": context.context_id if context else None,
        })

        return buddy

    def remove_buddy(self, buddy_id: str) -> bool:
        """Remove a buddy from the team."""
        if buddy_id in self._buddies:
            del self._buddies[buddy_id]
            return True
        return False

    def get_buddy(self, buddy_id: str) -> Optional[BuddyAgent]:
        """Get a buddy by ID."""
        return self._buddies.get(buddy_id)

    def list_buddies(self, context_id: Optional[str] = None) -> List[BuddyAgent]:
        """List all buddies, optionally filtered by context."""
        if context_id:
            return [b for b in self._buddies.values()
                    if b.context and b.context.context_id == context_id]
        return list(self._buddies.values())

    async def delegate(self, context_id: str, instruction: str,
                       roles: Optional[List[BuddyRole]] = None) -> Dict[str, str]:
        """Delegate an instruction to all buddies in a context.

        Each buddy in the context executes the instruction according
        to their role. Results are collected and returned.

        Args:
            context_id: The shared context ID.
            instruction: The instruction to delegate.
            roles: Optional filter by roles.

        Returns:
            Dict mapping buddy_id to response string.
        """
        ctx = self._contexts.get(context_id)
        if not ctx:
            raise ValueError(f"Context {context_id} not found")

        team = self.list_buddies(context_id)
        if roles:
            team = [b for b in team if b.role in roles]

        results = {}
        for buddy in team:
            try:
                response = await buddy.execute(instruction)
                results[buddy.buddy_id] = response
            except Exception as exc:
                results[buddy.buddy_id] = f"Error: {exc}"

        self._publish_event("claude.infra.buddy.context.shared", {
            "context_id": context_id,
            "instruction": instruction,
            "respondents": len(results),
        })

        return results

    async def team_review(self, context_id: str, content: str) -> Dict[str, Any]:
        """Have all buddies review content and collect feedback.

        Args:
            context_id: The shared context ID.
            content: Content to review.

        Returns:
            Aggregated review results.
        """
        ctx = self._contexts.get(context_id)
        if not ctx:
            raise ValueError(f"Context {context_id} not found")

        team = self.list_buddies(context_id)
        reviews = []
        all_approved = True

        for buddy in team:
            try:
                review = await buddy.review(content)
                reviews.append(review)
                if not review.get("approved", True):
                    all_approved = False
            except Exception as exc:
                reviews.append({"reviewer": buddy.name, "error": str(exc)})
                all_approved = False

        return {
            "approved": all_approved,
            "reviews": reviews,
            "reviewer_count": len(team),
        }

    def get_team_stats(self, context_id: str) -> Dict[str, Any]:
        """Get statistics for a team."""
        ctx = self._contexts.get(context_id)
        if not ctx:
            return {}
        team = self.list_buddies(context_id)
        return {
            "context_id": context_id,
            "task": ctx.task,
            "member_count": len(team),
            "roles": [b.role.value for b in team],
            "message_count": len(ctx.conversation),
            "artifact_count": len(ctx.artifacts),
        }

    def _publish_event(self, topic: str, payload: Dict[str, Any]) -> None:
        """Publish an event if the event bus is wired."""
        if self._event_bus is not None:
            self._event_bus.publish(
                Event.create(topic, "agent_infra", payload)
            )

    @property
    def buddy_count(self) -> int:
        return len(self._buddies)

    @property
    def context_count(self) -> int:
        return len(self._contexts)

    @property
    def status(self) -> HealthStatus:
        return self._status