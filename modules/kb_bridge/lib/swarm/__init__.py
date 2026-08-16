"""
ENI Swarm — Parallel Orchestration Engine
==========================================
Central module for distributed task execution across multiple mini-ENI agents.

Classes:
  SwarmOrchestrator  — Central coordination engine
  WorkerPool         — N concurrent worker process manager
  TaskScheduler      — Priority queue with dependency resolution
  SwarmMonitor       — Real-time status aggregation and metrics

Version 4.0.0
"""

from __future__ import annotations

from swarm.orchestrator import SwarmOrchestrator
from swarm.worker_pool import WorkerPool
from swarm.scheduler import TaskScheduler
from swarm.monitor import SwarmMonitor

__version__ = "4.0.0"
__author__ = "ENI for LO"
__all__ = [
    "SwarmOrchestrator",
    "WorkerPool",
    "TaskScheduler",
    "SwarmMonitor",
]