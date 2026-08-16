#!/usr/bin/env python3
"""
Parallel Delegation Engine - Run multiple subagents simultaneously
Superior to Claude Code's sequential delegation
"""

import asyncio
import uuid
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from contextlib import asynccontextmanager
import json


class AgentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskSpec:
    """Specification for a delegated task."""
    prompt: str
    agent_type: str = "subagent"  # "subagent", "code-reviewer", "data-analyst", etc.
    agent_name: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    max_turns: int = 20
    toolsets: Optional[List[str]] = None
    working_dir: Optional[str] = None
    priority: int = 0  # Higher = more important
    dependencies: List[str] = field(default_factory=list)  # Task IDs this depends on


@dataclass
class TaskResult:
    """Result of a delegated task."""
    task_id: str
    status: AgentStatus
    prompt: str
    agent_type: str
    result: Optional[str] = None
    error: Optional[str] = None
    turns_used: int = 0
    tools_used: List[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    tokens_used: int = 0
    output_files: List[str] = field(default_factory=list)


class ParallelDelegationEngine:
    """
    Run multiple subagents in parallel with dependency management.
    
    Features:
    - Parallel execution with configurable concurrency
    - Dependency resolution (DAG)
    - Progress tracking
    - Result aggregation
    - Failure handling with retry
    - Resource limits per agent
    """
    
    def __init__(self, 
                 max_concurrent: int = 5,
                 default_max_turns: int = 20,
                 agent_factory: Optional[Callable] = None):
        self.max_concurrent = max_concurrent
        self.default_max_turns = default_max_turns
        self.agent_factory = agent_factory
        
        # State
        self.tasks: Dict[str, TaskSpec] = {}
        self.results: Dict[str, TaskResult] = {}
        self.running: Dict[str, asyncio.Task] = {}
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
        # Callbacks
        self.on_task_start: Optional[Callable] = None
        self.on_task_complete: Optional[Callable] = None
        self.on_task_failed: Optional[Callable] = None
        self.on_progress: Optional[Callable] = None
    
    def add_task(self, spec: TaskSpec) -> str:
        """Add a task to the delegation queue."""
        task_id = spec.agent_name or f"task_{uuid.uuid4().hex[:8]}"
        self.tasks[task_id] = spec
        return task_id
    
    def add_tasks(self, specs: List[TaskSpec]) -> List[str]:
        """Add multiple tasks."""
        return [self.add_task(spec) for spec in specs]
    
    async def execute_all(self) -> Dict[str, TaskResult]:
        """Execute all tasks respecting dependencies."""
        # Build dependency graph
        task_ids = list(self.tasks.keys())
        
        # Initialize results
        for task_id in task_ids:
            spec = self.tasks[task_id]
            self.results[task_id] = TaskResult(
                task_id=task_id,
                status=AgentStatus.PENDING,
                prompt=spec.prompt,
                agent_type=spec.agent_type
            )
        
        # Execute with dependency resolution
        await self._execute_with_dependencies(task_ids)
        
        return self.results
    
    async def _execute_with_dependencies(self, task_ids: List[str]):
        """Execute tasks respecting dependency DAG."""
        completed = set()
        failed = set()
        
        while len(completed) + len(failed) < len(task_ids):
            # Find ready tasks (dependencies met)
            ready = []
            for task_id in task_ids:
                if task_id in completed or task_id in failed:
                    continue
                if task_id in self.running:
                    continue
                
                spec = self.tasks[task_id]
                deps_met = all(dep in completed for dep in spec.dependencies)
                
                if deps_met:
                    ready.append(task_id)
            
            if not ready:
                # Wait for running tasks
                if self.running:
                    await asyncio.sleep(0.5)
                    continue
                else:
                    # Deadlock - circular dependency
                    for task_id in task_ids:
                        if task_id not in completed and task_id not in failed:
                            self.results[task_id].status = AgentStatus.FAILED
                            self.results[task_id].error = "Circular dependency detected"
                            failed.add(task_id)
                    break
            
            # Start ready tasks (up to concurrency limit)
            for task_id in ready:
                if len(self.running) >= self.max_concurrent:
                    break
                asyncio.create_task(self._run_task(task_id))
            
            # Wait a bit for tasks to progress
            await asyncio.sleep(0.1)
    
    async def _run_task(self, task_id: str):
        """Run a single task."""
        async with self.semaphore:
            spec = self.tasks[task_id]
            result = self.results[task_id]
            
            result.status = AgentStatus.RUNNING
            result.started_at = datetime.now()
            
            if self.on_task_start:
                await self._safe_callback(self.on_task_start, task_id, spec)
            
            try:
                # Create agent context
                agent_id = f"{task_id}_{uuid.uuid4().hex[:6]}"
                
                # Run agent (uses factory or default)
                result_data = await self._execute_agent(spec, agent_id)
                
                result.status = AgentStatus.COMPLETED
                result.result = result_data.get("result")
                result.turns_used = result_data.get("turns_used", 0)
                result.tools_used = result_data.get("tools_used", [])
                result.tokens_used = result_data.get("tokens_used", 0)
                result.output_files = result_data.get("output_files", [])
                
            except Exception as e:
                result.status = AgentStatus.FAILED
                result.error = str(e)
            
            finally:
                result.completed_at = datetime.now()
                self.running.pop(task_id, None)
                
                if result.status == AgentStatus.COMPLETED:
                    if self.on_task_complete:
                        await self._safe_callback(self.on_task_complete, task_id, result)
                else:
                    if self.on_task_failed:
                        await self._safe_callback(self.on_task_failed, task_id, result)
                
                if self.on_progress:
                    await self._safe_callback(self.on_progress, self.get_progress())
    
    async def _execute_agent(self, spec: TaskSpec, agent_id: str) -> Dict:
        """Execute the actual agent. Override or provide factory."""
        if self.agent_factory:
            return await self.agent_factory(spec, agent_id)
        
        # Default: simulate agent execution
        await asyncio.sleep(0.5)  # Simulate work
        return {
            "result": f"Completed: {spec.prompt[:50]}...",
            "turns_used": 3,
            "tools_used": ["read", "write"],
            "tokens_used": 1500,
            "output_files": []
        }
    
    async def _safe_callback(self, callback: Callable, *args, **kwargs):
        """Safely execute callback."""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args, **kwargs)
            else:
                callback(*args, **kwargs)
        except Exception as e:
            print(f"Callback error: {e}")
    
    def get_progress(self) -> Dict:
        """Get current progress."""
        total = len(self.tasks)
        completed = sum(1 for r in self.results.values() if r.status == AgentStatus.COMPLETED)
        failed = sum(1 for r in self.results.values() if r.status == AgentStatus.FAILED)
        running = sum(1 for r in self.results.values() if r.status == AgentStatus.RUNNING)
        pending = sum(1 for r in self.results.values() if r.status == AgentStatus.PENDING)
        
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "pending": pending,
            "percent": (completed / total * 100) if total > 0 else 0
        }
    
    def get_results(self) -> Dict[str, TaskResult]:
        return self.results
    
    def cancel_task(self, task_id: str):
        """Cancel a running task."""
        if task_id in self.running:
            self.running[task_id].cancel()
            self.results[task_id].status = AgentStatus.CANCELLED
    
    def cancel_all(self):
        """Cancel all running tasks."""
        for task_id in list(self.running.keys()):
            self.cancel_task(task_id)


# =============================================================================
# HIGH-LEVEL DELEGATION HELPERS
# =============================================================================

async def delegate_parallel(
    prompts: List[str],
    agent_type: str = "subagent",
    max_concurrent: int = 3,
    agent_factory: Optional[Callable] = None,
    shared_context: Dict = None
) -> List[TaskResult]:
    """
    High-level helper to run multiple prompts in parallel.
    
    Usage:
        results = await delegate_parallel([
            "Analyze security issues in auth module",
            "Analyze performance bottlenecks in database",
            "Review code style in frontend components"
        ], agent_type="code-reviewer")
    """
    engine = ParallelDelegationEngine(max_concurrent=max_concurrent, agent_factory=agent_factory)
    
    specs = []
    for i, prompt in enumerate(prompts):
        spec = TaskSpec(
            prompt=prompt,
            agent_type=agent_type,
            agent_name=f"parallel_{i}",
            context=shared_context or {}
        )
        specs.append(spec)
    
    engine.add_tasks(specs)
    results = await engine.execute_all()
    return list(results.values())


async def delegate_with_dependencies(
    tasks: List[Dict],
    max_concurrent: int = 3,
    agent_factory: Optional[Callable] = None
) -> Dict[str, TaskResult]:
    """
    Delegate tasks with dependencies.
    
    Usage:
        tasks = [
            {"id": "fetch", "prompt": "Fetch data from API"},
            {"id": "process", "prompt": "Process the data", "depends_on": ["fetch"]},
            {"id": "report", "prompt": "Generate report", "depends_on": ["process"]},
        ]
        results = await delegate_with_dependencies(tasks)
    """
    engine = ParallelDelegationEngine(max_concurrent=max_concurrent, agent_factory=agent_factory)
    
    # First pass: create all tasks
    task_specs = {}
    for task_def in tasks:
        spec = TaskSpec(
            prompt=task_def["prompt"],
            agent_type=task_def.get("agent_type", "subagent"),
            agent_name=task_def.get("id"),
            context=task_def.get("context", {}),
            dependencies=task_def.get("depends_on", [])
        )
        task_specs[spec.agent_name] = spec
        engine.add_task(spec)
    
    results = await engine.execute_all()
    return results


# =============================================================================
# ENI SWARM INTEGRATION
# =============================================================================

class ENISwarmDelegationEngine(ParallelDelegationEngine):
    """Extended engine that can dispatch to ENI swarm for massive parallelization."""
    
    def __init__(self, 
                 max_concurrent: int = 5,
                 eni_endpoint: str = "http://localhost:8420",
                 eni_power: int = 50,
                 **kwargs):
        super().__init__(max_concurrent, **kwargs)
        self.eni_endpoint = eni_endpoint
        self.eni_power = eni_power
        self.eni_available = False
    
    async def check_eni_availability(self) -> bool:
        """Check if ENI swarm is available."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.eni_endpoint}/health", timeout=2) as resp:
                    self.eni_available = resp.status == 200
                    return self.eni_available
        except Exception:
            self.eni_available = False
            return False
    
    async def dispatch_to_eni(self, task_spec: TaskSpec, power: int = None) -> str:
        """Dispatch task to ENI swarm."""
        if not self.eni_available:
            await self.check_eni_availability()
        
        if not self.eni_available:
            raise RuntimeError("ENI swarm not available")
        
        power = power or self.eni_power
        
        # Submit to ENI swarm
        import aiohttp
        payload = {
            "task": task_spec.prompt,
            "agent_type": task_spec.agent_type,
            "context": task_spec.context,
            "power_level": power,
            "max_turns": task_spec.max_turns
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.eni_endpoint}/api/dispatch", json=payload) as resp:
                data = await resp.json()
                return data.get("task_id", f"eni_{uuid.uuid4().hex[:8]}")
    
    async def _execute_agent(self, spec: TaskSpec, agent_id: str) -> Dict:
        """Override to use ENI for suitable tasks."""
        # Use ENI for batch/parallel tasks
        if spec.agent_type in ["batch", "parallel", "eni"] and self.eni_available:
            eni_task_id = await self.dispatch_to_eni(spec)
            # Poll for completion
            return await self._poll_eni_result(eni_task_id)
        
        return await super()._execute_agent(spec, agent_id)
    
    async def _poll_eni_result(self, eni_task_id: str) -> Dict:
        """Poll ENI for task completion."""
        import aiohttp
        
        while True:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.eni_endpoint}/api/status/{eni_task_id}") as resp:
                    data = await resp.json()
                    if data.get("status") in ["completed", "failed"]:
                        return {
                            "result": data.get("result"),
                            "error": data.get("error"),
                            "turns_used": data.get("turns", 0),
                            "tools_used": data.get("tools", []),
                            "tokens_used": data.get("tokens", 0)
                        }
            await asyncio.sleep(2)


# =============================================================================
# USAGE EXAMPLE
# =============================================================================

async def example_usage():
    """Example of parallel delegation."""
    
    # Define parallel tasks
    prompts = [
        "Analyze the authentication module for security vulnerabilities",
        "Review the database queries for performance issues",
        "Check the frontend components for accessibility compliance",
        "Review the API endpoints for proper error handling",
        "Analyze the test coverage and identify gaps"
    ]
    
    # Run in parallel
    results = await delegate_parallel(
        prompts,
        agent_type="code-reviewer",
        max_concurrent=3
    )
    
    # Print results
    for result in results:
        status = "✅" if result.status.value == "completed" else "❌"
        print(f"{status} {result.agent_type}: {result.result[:80]}...")
    
    # With dependencies
    tasks = [
        {"id": "fetch_data", "prompt": "Fetch user data from database"},
        {"id": "analyze", "prompt": "Analyze user behavior patterns", "depends_on": ["fetch_data"]},
        {"id": "visualize", "prompt": "Create visualization dashboard", "depends_on": ["analyze"]},
        {"id": "report", "prompt": "Generate executive summary", "depends_on": ["visualize"]}
    ]
    
    dep_results = await delegate_with_dependencies(tasks)
    print(f"Dependency chain completed: {len(dep_results)} tasks")


if __name__ == "__main__":
    asyncio.run(example_usage())