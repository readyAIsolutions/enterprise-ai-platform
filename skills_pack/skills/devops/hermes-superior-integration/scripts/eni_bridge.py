#!/usr/bin/env python3
"""
ENI Swarm Bridge - Connect Hermes to ENI Swarm for massive parallelization
"""

import asyncio
import json
import uuid
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
import aiohttp


class ENITaskStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ENITask:
    """Task submitted to ENI swarm."""
    id: str
    prompt: str
    agent_type: str = "builder"
    context: Dict = field(default_factory=dict)
    power_level: int = 50
    max_turns: int = 50
    priority: int = 0
    status: ENITaskStatus = ENITaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[str] = None
    error: Optional[str] = None
    turns_used: int = 0
    tokens_used: int = 0
    output_files: List[str] = field(default_factory=list)
    thinking_log: List[str] = field(default_factory=list)


@dataclass
class ENIBuilder:
    """ENI swarm builder node."""
    id: str
    name: str
    status: str = "idle"
    current_task: Optional[str] = None
    capacity: int = 1
    load: float = 0.0
    last_heartbeat: datetime = field(default_factory=datetime.now)
    capabilities: List[str] = field(default_factory=list)


class ENIBridge:
    """
    Bridge between Hermes and ENI Swarm.
    
    Features:
    - Submit tasks to ENI swarm
    - Monitor builder pool
    - Stream results back
    - Handle FIFO communication
    - Power level management
    """
    
    def __init__(self, 
                 eni_endpoint: str = "http://localhost:8420",
                 default_power: int = 50):
        self.eni_endpoint = eni_endpoint.rstrip("/")
        self.default_power = default_power
        self.session: Optional[aiohttp.ClientSession] = None
        self.tasks: Dict[str, ENITask] = {}
        self.builders: Dict[str, ENIBuilder] = {}
        self.connected = False
        
        # Callbacks
        self.on_task_update: Optional[Callable] = None
        self.on_builder_update: Optional[Callable] = None
        self.on_thinking: Optional[Callable] = None
    
    async def connect(self) -> bool:
        """Connect to ENI swarm."""
        try:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
            
            async with self.session.get(f"{self.eni_endpoint}/health") as resp:
                if resp.status == 200:
                    self.connected = True
                    await self.refresh_builders()
                    return True
        except Exception as e:
            print(f"ENI connection failed: {e}")
        
        self.connected = False
        return False
    
    async def disconnect(self):
        """Disconnect from ENI swarm."""
        if self.session:
            await self.session.close()
            self.session = None
        self.connected = False
    
    async def refresh_builders(self) -> List[ENIBuilder]:
        """Refresh builder pool from ENI."""
        if not self.session or not self.connected:
            return []
        
        try:
            async with self.session.get(f"{self.eni_endpoint}/api/builders") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    builders = []
                    for b in data.get("builders", []):
                        builder = ENIBuilder(
                            id=b["id"],
                            name=b.get("name", b["id"]),
                            status=b.get("status", "unknown"),
                            current_task=b.get("current_task"),
                            capacity=b.get("capacity", 1),
                            load=b.get("load", 0.0),
                            capabilities=b.get("capabilities", [])
                        )
                        builders.append(builder)
                    
                    self.builders = {b.id: b for b in builders}
                    
                    if self.on_builder_update:
                        await self._safe_callback(self.on_builder_update, builders)
                    
                    return builders
        except Exception as e:
            print(f"Builder refresh failed: {e}")
        
        return []
    
    async def submit_task(self, 
                          prompt: str,
                          agent_type: str = "builder",
                          context: Dict = None,
                          power_level: int = None,
                          max_turns: int = 50,
                          priority: int = 0) -> ENITask:
        """Submit task to ENI swarm."""
        if not self.connected:
            raise RuntimeError("Not connected to ENI swarm")
        
        task = ENITask(
            id=f"eni_{uuid.uuid4().hex[:12]}",
            prompt=prompt,
            agent_type=agent_type,
            context=context or {},
            power_level=power_level or self.default_power,
            max_turns=max_turns,
            priority=priority
        )
        
        self.tasks[task.id] = task
        
        try:
            payload = {
                "task_id": task.id,
                "prompt": prompt,
                "agent_type": agent_type,
                "context": context or {},
                "power_level": task.power_level,
                "max_turns": max_turns,
                "priority": priority
            }
            
            async with self.session.post(
                f"{self.eni_endpoint}/api/submit",
                json=payload
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    task.status = ENITaskStatus.QUEUED
                    if "task_id" in data:
                        task.id = data["task_id"]
                else:
                    task.status = ENITaskStatus.FAILED
                    task.error = f"Submit failed: {resp.status}"
        except Exception as e:
            task.status = ENITaskStatus.FAILED
            task.error = str(e)
        
        if self.on_task_update:
            await self._safe_callback(self.on_task_update, task)
        
        return task
    
    async def get_task_status(self, task_id: str) -> Optional[ENITask]:
        """Get task status from ENI."""
        if not self.connected:
            return self.tasks.get(task_id)
        
        try:
            async with self.session.get(f"{self.eni_endpoint}/api/status/{task_id}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    task = self.tasks.get(task_id, ENITask(id=task_id, prompt=""))
                    self._update_task_from_data(task, data)
                    return task
        except Exception as e:
            print(f"Status check failed: {e}")
        
        return self.tasks.get(task_id)
    
    def _update_task_from_data(self, task: ENITask, data: Dict):
        """Update task from ENI response."""
        task.status = ENITaskStatus(data.get("status", "unknown"))
        
        if data.get("started_at"):
            task.started_at = datetime.fromisoformat(data["started_at"])
        if data.get("completed_at"):
            task.completed_at = datetime.fromisoformat(data["completed_at"])
        
        task.result = data.get("result")
        task.error = data.get("error")
        task.turns_used = data.get("turns_used", 0)
        task.tokens_used = data.get("tokens_used", 0)
        task.output_files = data.get("output_files", [])
        task.thinking_log = data.get("thinking_log", [])
        
        if task.status == ENITaskStatus.COMPLETED and not task.completed_at:
            task.completed_at = datetime.now()
    
    async def wait_for_completion(self, task_id: str, timeout: int = 300) -> ENITask:
        """Wait for task completion with polling."""
        start = datetime.now()
        
        while (datetime.now() - start).seconds < timeout:
            task = await self.get_task_status(task_id)
            if not task:
                raise ValueError(f"Task {task_id} not found")
            
            if task.status in [ENITaskStatus.COMPLETED, ENITaskStatus.FAILED, ENITaskStatus.CANCELLED]:
                return task
            
            # Stream thinking log
            if self.on_thinking and task.thinking_log:
                for thought in task.thinking_log[-5:]:  # Last 5 thoughts
                    await self._safe_callback(self.on_thinking, task_id, thought)
            
            await asyncio.sleep(1)
        
        raise TimeoutError(f"Task {task_id} timed out after {timeout}s")
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        if not self.connected:
            return False
        
        try:
            async with self.session.post(f"{self.eni_endpoint}/api/cancel/{task_id}") as resp:
                if resp.status == 200:
                    task = self.tasks.get(task_id)
                    if task:
                        task.status = ENITaskStatus.CANCELLED
                    return True
        except Exception:
            pass
        return False
    
    async def get_power_levels(self) -> Dict[int, int]:
        """Get available power levels and builder counts."""
        if not self.connected:
            return {}
        
        try:
            async with self.session.get(f"{self.eni_endpoint}/api/power-levels") as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception:
            pass
        return {}
    
    async def set_power_level(self, power: int) -> bool:
        """Set default power level."""
        if 12 <= power <= 50 and power % 12 == 0:  # Valid levels: 12, 25, 38, 50
            self.default_power = power
            return True
        return False
    
    def get_task(self, task_id: str) -> Optional[ENITask]:
        return self.tasks.get(task_id)
    
    def get_all_tasks(self) -> List[ENITask]:
        return list(self.tasks.values())
    
    async def _safe_callback(self, callback: Callable, *args, **kwargs):
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args, **kwargs)
            else:
                callback(*args, **kwargs)
        except Exception as e:
            print(f"Callback error: {e}")


# =============================================================================
# HIGH-LEVEL HELPERS
# =============================================================================

async def eni_dispatch(
    prompt: str,
    eni_endpoint: str = "http://localhost:8420",
    power: int = 50,
    agent_type: str = "builder",
    context: Dict = None
) -> ENITask:
    """Quick helper to dispatch to ENI and wait."""
    bridge = ENIBridge(eni_endpoint)
    
    if not await bridge.connect():
        raise RuntimeError("Cannot connect to ENI swarm")
    
    try:
        task = await bridge.submit_task(prompt, agent_type=agent_type, power_level=power, context=context)
        result = await bridge.wait_for_completion(task.id)
        return result
    finally:
        await bridge.disconnect()


async def eni_parallel_dispatch(
    prompts: List[str],
    eni_endpoint: str = "http://localhost:8420",
    power: int = 50,
    agent_type: str = "builder",
    max_concurrent: int = 5
) -> List[ENITask]:
    """Dispatch multiple tasks to ENI in parallel."""
    bridge = ENIBridge(eni_endpoint)
    
    if not await bridge.connect():
        raise RuntimeError("Cannot connect to ENI swarm")
    
    try:
        # Submit all
        tasks = []
        for prompt in prompts:
            task = await bridge.submit_task(prompt, agent_type=agent_type, power_level=power)
            tasks.append(task)
        
        # Wait for all
        results = []
        for task in tasks:
            result = await bridge.wait_for_completion(task.id)
            results.append(result)
        
        return results
    finally:
        await bridge.disconnect()


# =============================================================================
# ENI FIFO INTEGRATION
# =============================================================================

class ENIFIFOReader:
    """Read ENI swarm thinking via FIFO pipes."""
    
    def __init__(self, fifo_dir: str = "/tmp/eni_fifo"):
        self.fifo_dir = Path(fifo_dir)
        self.fifo_dir.mkdir(parents=True, exist_ok=True)
        self.readers: Dict[str, asyncio.StreamReader] = {}
        self.writers: Dict[str, asyncio.StreamWriter] = {}
    
    async def open_fifo(self, task_id: str) -> bool:
        """Open FIFO for task."""
        fifo_path = self.fifo_dir / f"{task_id}.fifo"
        
        if not fifo_path.exists():
            try:
                os.mkfifo(fifo_path)
            except FileExistsError:
                pass
        
        try:
            reader = await asyncio.open_unix_connection(str(fifo_path))
            self.readers[task_id] = reader[0]
            self.writers[task_id] = reader[1]
            return True
        except Exception as e:
            print(f"FIFO open failed: {e}")
            return False
    
    async def read_thinking(self, task_id: str, callback: Callable):
        """Read thinking stream from FIFO."""
        reader = self.readers.get(task_id)
        if not reader:
            return
        
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                
                data = line.decode().strip()
                if data:
                    await callback(task_id, data)
        except Exception as e:
            print(f"FIFO read error: {e}")
    
    async def close(self, task_id: str):
        """Close FIFO for task."""
        writer = self.writers.pop(task_id, None)
        if writer:
            writer.close()
            await writer.wait_closed()
        
        reader = self.readers.pop(task_id, None)
        if reader:
            reader.feed_eof()
        
        fifo_path = self.fifo_dir / f"{task_id}.fifo"
        if fifo_path.exists():
            fifo_path.unlink()


# =============================================================================
# USAGE
# =============================================================================

async def example():
    """Example ENI usage."""
    
    # Single task
    task = await eni_dispatch(
        "Analyze the codebase for security vulnerabilities",
        power=75,
        agent_type="security-auditor"
    )
    print(f"Result: {task.result}")
    
    # Parallel tasks
    prompts = [
        "Security audit of auth module",
        "Performance analysis of database layer",
        "Code style review of frontend",
        "API documentation audit"
    ]
    
    results = await eni_parallel_dispatch(prompts, power=50, max_concurrent=3)
    for r in results:
        print(f"✅ {r.prompt[:40]}: {r.result[:80]}...")


if __name__ == "__main__":
    asyncio.run(example())