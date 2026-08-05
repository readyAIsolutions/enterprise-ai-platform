"""
ENI Swarm Enterprise Module v5.0.0
===================================
Enterprise Platform Kernel module for the ENI Swarm — the 50-builder
on-demand AI agent fleet coordinated by Master Driver v5.0.

Integrates swarm lifecycle management (spawn, status, pause/resume),
health monitoring, prompt enhancement via PromptForge, and event-driven
communication into the Enterprise AI OS.

Architecture:
  ENISwarmModule (Module)
  ├── SwarmBridge      — lifecycle, status, task management
  ├── SwarmHealthCheck  — continuous health monitoring & metrics
  └── PromptForgeBridge — wraps PromptForge for enterprise prompt enhancement

Events emitted:
  - swarm.builder.started     — a builder began executing a task
  - swarm.builder.completed   — a builder finished successfully
  - swarm.builder.failed      — a builder task failed or timed out
  - swarm.master.status       — master driver reported status update
  - swarm.health.degraded     — one or more builders unhealthy
  - swarm.health.recovered    — swarm recovered from degraded state

Metrics tracked:
  - active_builders           — count of currently executing builders
  - completed_tasks           — cumulative successful task count
  - failure_rate              — ratio of failed vs total tasks (0.0-1.0)
  - avg_task_duration         — rolling average task duration in seconds

Compatible with:  ENI Swarm Dashboard (Starlette on :8420)
                  Master Driver v5.0 (eni.master_driver)
                  PromptForge v1.0 (eni.prompt_forge)
                  Enterprise Platform Kernel v1.0.0

License:  Proprietary — ENI AI OS
"""

__version__ = "5.0.0"

from .__module__ import (
    ENISwarmModule,
    SwarmHealthCheck,
)
from .heartbeat import (
    DEFAULT_HEARTBEAT_TIMEOUT,
    STATUS_ABSENT,
    STATUS_ALIVE,
    STATUS_LOST,
    FixedClock,
    HealthAggregator,
    HealthReport,
    HeartbeatProtocol,
    MemberRegistry,
    SwarmClock,
    SwarmHealth,
    SwarmMember,
)
from .prompt_forge_bridge import (
    EnhancedTask,
    PromptForgeBridge,
)
from .swarm_bridge import (
    BuilderStatus,
    SwarmBridge,
    SwarmConfig,
    SwarmMetrics,
)

__all__ = [
    # Core module class
    "ENISwarmModule",
    # Bridge (lifecycle + status)
    "SwarmBridge",
    "BuilderStatus",
    "SwarmMetrics",
    "SwarmConfig",
    # Health monitoring
    "SwarmHealthCheck",
    # PromptForge wrapper
    "PromptForgeBridge",
    "EnhancedTask",
    # Member heartbeat + liveness registry
    "SwarmMember",
    "MemberRegistry",
    "HeartbeatProtocol",
    "HealthAggregator",
    "HealthReport",
    "SwarmHealth",
    "SwarmClock",
    "FixedClock",
    "STATUS_ALIVE",
    "STATUS_ABSENT",
    "STATUS_LOST",
    "DEFAULT_HEARTBEAT_TIMEOUT",
]
