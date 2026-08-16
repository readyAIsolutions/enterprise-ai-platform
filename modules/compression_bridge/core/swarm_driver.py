#!/usr/bin/env python3
"""
ENI Impossible Swarm Driver - Self-Healing 20+ Worker Swarm
============================================================
Integrates: PAQ8, zstd, lz4, brotli, LLMLingua, headroom, claw-compactor,
Wenyan encoding, PXPipe steganography, Glyph caching, Adaptive ML selector
"""
import asyncio
import json
import hashlib
import time
import signal
import subprocess
import sys
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import threading
import queue

sys.path.insert(0, "/home/hunter/Desktop/eni_compression")

from core.engine import CompressionEngine, CompressionMode, CompressionResult
from core.selector import AdaptiveCompressorSelector


class WorkerState(Enum):
    IDLE = "idle"
    BUSY = "busy"
    HEALING = "healing"
    DEAD = "dead"
    STARTING = "starting"


@dataclass
class SwarmTask:
    task_id: str
    payload: bytes
    mode: CompressionMode
    priority: int = 0
    created_at: float = field(default_factory=time.time)
    retries: int = 0
    max_retries: int = 3
    callback: Optional[Callable] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkerStatus:
    worker_id: str
    state: WorkerState = WorkerState.IDLE
    current_task: Optional[str] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    last_heartbeat: float = field(default_factory=time.time)
    error_count: int = 0
    restart_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ImpossibleSwarmWorker:
    """Individual worker in the impossible swarm"""
    
    def __init__(self, worker_id: str, swarm: 'ImpossibleSwarm'):
        self.worker_id = worker_id
        self.swarm = swarm
        self.engine = CompressionEngine()
        self.selector = AdaptiveCompressorSelector()
        self.status = WorkerStatus(worker_id=worker_id)
        self._running = False
        self._task_queue: asyncio.Queue = asyncio.Queue()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    async def start(self):
        self._running = True
        self._loop = asyncio.get_running_loop()
        self.status.state = WorkerState.IDLE
        self.swarm.logger.info(f"Worker {self.worker_id} started")
        
        # Start heartbeat
        asyncio.create_task(self._heartbeat_loop())
        # Start task processor
        asyncio.create_task(self._process_loop())
    
    async def stop(self):
        self._running = False
        self.status.state = WorkerState.DEAD
        self.swarm.logger.info(f"Worker {self.worker_id} stopped")
    
    async def submit_task(self, task: SwarmTask):
        await self._task_queue.put(task)
    
    async def _heartbeat_loop(self):
        while self._running:
            self.status.last_heartbeat = time.time()
            await asyncio.sleep(5)
    
    async def _process_loop(self):
        while self._running:
            try:
                task = await asyncio.wait_for(self._task_queue.get(), timeout=1.0)
                await self._execute_task(task)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.swarm.logger.error(f"Worker {self.worker_id} process error: {e}")
                await asyncio.sleep(1)
    
    async def _execute_task(self, task: SwarmTask):
        self.status.state = WorkerState.BUSY
        self.status.current_task = task.task_id
        start_time = time.time()
        
        try:
            result = await self._compress_with_mode(task.payload, task.mode)
            
            # Store result in swarm's results dict for get_result()
            self.swarm.results[task.task_id] = result
            
            if task.callback:
                await task.callback(result)
            
            self.status.tasks_completed += 1
            self.swarm._stats["completed"] += 1
            self.swarm.logger.info(f"Worker {self.worker_id} completed task {task.task_id} in {time.time() - start_time:.2f}s")
            
        except Exception as e:
            self.status.tasks_failed += 1
            self.status.error_count += 1
            self.swarm._stats["failed"] += 1
            self.swarm.logger.error(f"Worker {self.worker_id} failed task {task.task_id}: {e}")
            
            if task.retries < task.max_retries:
                task.retries += 1
                await self.swarm.task_queue.put(task)
            elif task.callback:
                await task.callback(CompressionResult(
                    success=False, original_size=len(task.payload), compressed_size=0,
                    ratio=0, mode=task.mode, error=str(e)
                ))
            else:
                # Store error result in swarm results
                self.swarm.results[task.task_id] = CompressionResult(
                    success=False, original_size=len(task.payload), compressed_size=0,
                    ratio=0, mode=task.mode, error=str(e)
                )
        
        finally:
            self.status.state = WorkerState.IDLE
            self.status.current_task = None
    
    async def _compress_with_mode(self, data: bytes, mode: CompressionMode) -> CompressionResult:
        # Run synchronous compression in thread pool
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.engine.compress, data, mode)


class ImpossibleSwarm:
    """Self-healing 20+ worker swarm for ENI Impossible Compression"""
    
    WORKER_TYPES = [
        ("paq8", 4, CompressionMode.MAXIMUM),
        ("zstd", 3, CompressionMode.BALANCED),
        ("lz4", 3, CompressionMode.FAST),
        ("brotli", 2, CompressionMode.BALANCED),
        ("llm", 2, CompressionMode.LLM_OPTIMIZED),
        ("code", 2, CompressionMode.CODE_AWARE),
        ("wenyan", 2, CompressionMode.WENYAN),
        ("pxpipe", 1, CompressionMode.STEGANOGRAPHY),
        ("glyph", 1, CompressionMode.GLYPH),
        ("adaptive", 2, CompressionMode.ADAPTIVE),
        ("impossible", 2, CompressionMode.IMPOSSIBLE),
    ]
    
    def __init__(self, num_workers: int = 24):
        self.num_workers = num_workers
        self.workers: Dict[str, ImpossibleSwarmWorker] = {}
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.results: Dict[str, CompressionResult] = {}
        self.logger = self._setup_logger()
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._healer_task: Optional[asyncio.Task] = None
        self._stats = {
            "submitted": 0, "completed": 0, "failed": 0,
            "retries": 0, "healings": 0, "start_time": time.time()
        }
    
    def _setup_logger(self):
        import logging
        logger = logging.getLogger("eni_swarm")
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s'
        ))
        logger.addHandler(handler)
        return logger
    
    async def start(self):
        self._running = True
        self.logger.info(f"Starting Impossible Swarm with {self.num_workers} workers")
        
        # Create workers based on types
        worker_id = 0
        for wtype, count, mode in self.WORKER_TYPES:
            for i in range(count):
                if worker_id >= self.num_workers:
                    break
                wid = f"{wtype}_{worker_id:02d}"
                worker = ImpossibleSwarmWorker(wid, self)
                self.workers[wid] = worker
                await worker.start()
                worker_id += 1
            if worker_id >= self.num_workers:
                break
        
        # Start task distributor
        self._distributor_task = asyncio.create_task(self._distributor_loop())
        
        # Start monitor and healer
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self._healer_task = asyncio.create_task(self._healer_loop())
        
        self.logger.info(f"All {len(self.workers)} workers started")
    
    async def stop(self):
        self._running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
        if self._healer_task:
            self._healer_task.cancel()
        if self._distributor_task:
            self._distributor_task.cancel()
        
        for worker in self.workers.values():
            await worker.stop()
        
        self.logger.info("Swarm stopped")
    
    async def submit(self, payload: bytes, mode: CompressionMode = CompressionMode.ADAPTIVE,
                    priority: int = 0, callback: Optional[Callable] = None) -> str:
        task_id = hashlib.sha256(f"{time.time()}{payload[:32]}".encode()).hexdigest()[:12]
        task = SwarmTask(
            task_id=task_id,
            payload=payload,
            mode=mode,
            priority=priority,
            callback=callback
        )
        
        await self.task_queue.put(task)
        self._stats["submitted"] += 1
        return task_id
    
    async def submit_batch(self, items: List[tuple], mode: CompressionMode = CompressionMode.ADAPTIVE) -> List[str]:
        task_ids = []
        for i, (payload, priority) in enumerate(items):
            task_id = await self.submit(payload, mode, priority)
            task_ids.append(task_id)
        return task_ids
    
    async def get_result(self, task_id: str, timeout: float = 300.0) -> Optional[CompressionResult]:
        start = time.time()
        while time.time() - start < timeout:
            if task_id in self.results:
                return self.results.pop(task_id)
            await asyncio.sleep(0.1)
        return None
    
    async def compress(self, data: bytes, mode: CompressionMode = CompressionMode.ADAPTIVE) -> CompressionResult:
        future = asyncio.Future()
        
        def callback(result):
            future.set_result(result)
        
        await self.submit(data, mode, callback=callback)
        return await future
    
    async def _healer_loop(self):
        while self._running:
            await asyncio.sleep(30)
            await self._heal_workers()
    
    async def _distributor_loop(self):
        """Distribute tasks from central queue to idle workers"""
        while self._running:
            try:
                # Get task from central queue with timeout
                task = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)
                
                # Find idle worker
                idle_worker = None
                for worker in self.workers.values():
                    if worker.status.state == WorkerState.IDLE:
                        idle_worker = worker
                        break
                
                if idle_worker:
                    # Submit to worker
                    await idle_worker.submit_task(task)
                else:
                    # No idle workers, put back in queue
                    await self.task_queue.put(task)
                    await asyncio.sleep(0.1)
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"Distributor error: {e}")
                await asyncio.sleep(0.1)
    
    async def _monitor_loop(self):
        while self._running:
            await asyncio.sleep(10)
            self._print_status()
    
    async def _heal_workers(self):
        now = time.time()
        for worker_id, worker in list(self.workers.items()):
            status = worker.status
            
            # Check if worker is stuck
            if status.state == WorkerState.BUSY and now - status.last_heartbeat > 120:
                self.logger.warning(f"Worker {worker_id} stuck, restarting...")
                await self._restart_worker(worker_id)
                self._stats["healings"] += 1
            
            # Check if worker is dead
            elif status.state == WorkerState.DEAD or now - status.last_heartbeat > 300:
                self.logger.warning(f"Worker {worker_id} dead, replacing...")
                await self._replace_worker(worker_id)
                self._stats["healings"] += 1
            
            # Check error rate
            elif status.tasks_completed > 0 and status.tasks_failed / status.tasks_completed > 0.5:
                self.logger.warning(f"Worker {worker_id} high error rate, restarting...")
                await self._restart_worker(worker_id)
                self._stats["healings"] += 1
    
    async def _restart_worker(self, worker_id: str):
        worker = self.workers.get(worker_id)
        if worker:
            await worker.stop()
            new_worker = ImpossibleSwarmWorker(worker_id, self)
            self.workers[worker_id] = new_worker
            await new_worker.start()
            new_worker.status.restart_count = worker.status.restart_count + 1
    
    async def _replace_worker(self, worker_id: str):
        await self._restart_worker(worker_id)
    
    def _print_status(self):
        states = {}
        for w in self.workers.values():
            states[w.status.state.value] = states.get(w.status.state.value, 0) + 1
        
        uptime = time.time() - self._stats["start_time"]
        self.logger.info(
            f"SWARM STATUS | Uptime: {uptime:.0f}s | "
            f"Submitted: {self._stats['submitted']} | "
            f"Completed: {self._stats['completed']} | "
            f"Failed: {self._stats['failed']} | "
            f"Healings: {self._stats['healings']} | "
            f"States: {states}"
        )
    
    def get_stats(self) -> Dict[str, Any]:
        worker_stats = {}
        for wid, w in self.workers.items():
            worker_stats[wid] = {
                "state": w.status.state.value,
                "completed": w.status.tasks_completed,
                "failed": w.status.tasks_failed,
                "restarts": w.status.restart_count,
                "errors": w.status.error_count
            }
        
        return {
            "swarm": self._stats,
            "workers": worker_stats,
            "queue_size": self.task_queue.qsize()
        }


async def demo():
    """Demonstrate the impossible swarm"""
    swarm = ImpossibleSwarm(num_workers=24)
    await swarm.start()
    
    # Test data
    test_texts = [
        b"Hello world! " * 100,
        b'{"json": "data", "array": [1,2,3,4,5]}' * 50,
        b"def fibonacci(n): return n if n <= 1 else fibonacci(n-1) + fibonacci(n-2)" * 20,
        b"SELECT * FROM users WHERE active = 1 ORDER BY created_at DESC LIMIT 100" * 10,
        b"Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 30,
    ]
    
    # Submit all
    task_ids = []
    for i, text in enumerate(test_texts):
        task_id = await swarm.submit(text, CompressionMode.IMPOSSIBLE)
        task_ids.append(task_id)
    
    # Get results
    results = []
    for task_id in task_ids:
        result = await swarm.get_result(task_id)
        results.append(result)
        if result:
            print(f"Task {task_id}: {result.ratio:.2f}x ratio, {result.compressed_size} bytes")
    
    # Print stats
    print(json.dumps(swarm.get_stats(), indent=2))
    
    await swarm.stop()


if __name__ == "__main__":
    asyncio.run(demo())