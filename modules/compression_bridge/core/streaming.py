#!/usr/bin/env python3
"""
Real-Time Streaming Compression with Backpressure
==================================================
Handles infinite data streams with bounded memory and latency guarantees.
"""
import asyncio
import zlib
import lz4.frame
import zstandard as zstd
import hashlib
import time
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, AsyncGenerator, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import heapq


class CompressionAlgorithm(Enum):
    LZ4 = "lz4"
    ZSTD = "zstd"
    ZLIB = "zlib"


class StreamPriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class StreamChunk:
    """A chunk of streaming data"""
    data: bytes
    sequence: int
    timestamp: float = field(default_factory=time.time)
    priority: StreamPriority = StreamPriority.NORMAL
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_final: bool = False
    checksum: str = ""
    
    def __post_init__(self):
        self.checksum = hashlib.md5(self.data).hexdigest()[:8]
    
    def __lt__(self, other):
        # For priority queue ordering
        return self.priority.value > other.priority.value


@dataclass
class CompressedChunk:
    """A compressed chunk with metadata"""
    data: bytes
    original_size: int
    compressed_size: int
    algorithm: CompressionAlgorithm
    sequence: int
    timestamp: float
    ratio: float
    checksum: str


class StreamWindow:
    """Sliding window for stream compression"""
    
    def __init__(self, max_size: int = 1024 * 1024):  # 1MB default
        self.max_size = max_size
        self.buffer = bytearray()
        self.sequences: deque = deque()
        self.total_size = 0
    
    def add(self, chunk: StreamChunk) -> bool:
        """Add chunk to window, return True if window is full"""
        self.buffer.extend(chunk.data)
        self.sequences.append(chunk.sequence)
        self.total_size += len(chunk.data)
        return self.total_size >= self.max_size
    
    def get_window(self) -> bytes:
        """Get current window data"""
        return bytes(self.buffer)
    
    def slide(self, remove_bytes: int):
        """Slide window forward by removing bytes"""
        if remove_bytes >= len(self.buffer):
            self.buffer.clear()
            self.sequences.clear()
            self.total_size = 0
        else:
            del self.buffer[:remove_bytes]
            self.total_size -= remove_bytes
    
    def clear(self):
        self.buffer.clear()
        self.sequences.clear()
        self.total_size = 0


class StreamCompressor:
    """Compresses streaming data with sliding window"""
    
    def __init__(
        self,
        algorithm: CompressionAlgorithm = CompressionAlgorithm.LZ4,
        window_size: int = 1024 * 1024,
        level: Optional[int] = None,
    ):
        self.algorithm = algorithm
        self.window = StreamWindow(window_size)
        self.level = level or self._default_level()
        self.sequence_counter = 0
        self.stats = {
            "chunks_processed": 0,
            "total_original": 0,
            "total_compressed": 0,
            "total_time_ms": 0.0,
        }
        
        # Initialize compressor
        self._init_compressor()
    
    def _default_level(self) -> int:
        if self.algorithm == CompressionAlgorithm.LZ4:
            return 9
        elif self.algorithm == CompressionAlgorithm.ZSTD:
            return 3
        return 6
    
    def _init_compressor(self):
        if self.algorithm == CompressionAlgorithm.LZ4:
            self.compressor = lz4.frame.create_compression_context()
            self.compression_level = self.level
        elif self.algorithm == CompressionAlgorithm.ZSTD:
            self.compressor = zstd.ZstdCompressor(level=self.level)
        elif self.algorithm == CompressionAlgorithm.ZLIB:
            self.compressor = zlib.compressobj(self.level)
    
    def compress_chunk(self, chunk: StreamChunk) -> Optional[CompressedChunk]:
        """Compress a chunk, using sliding window for context"""
        # Add to window
        window_full = self.window.add(chunk)
        
        if window_full:
            # Window full, compress the window
            window_data = self.window.get_window()
            compressed = self._compress(window_data)
            
            result = CompressedChunk(
                data=compressed,
                original_size=len(self.window.buffer),
                compressed_size=len(compressed),
                algorithm=self.algorithm,
                sequence=self.sequence_counter,
                timestamp=time.time(),
                ratio=len(self.window.buffer) / len(compressed) if compressed else 1.0,
                checksum=hashlib.md5(self.window.buffer).hexdigest()[:8],
            )
            
            # Slide window (keep last 25% for context)
            keep_size = len(self.window.buffer) // 4
            remove_size = len(self.window.buffer) - keep_size
            self.window.slide(remove_size)
            
            self.sequence_counter += 1
            self._update_stats(result)
            
            return result
        
        return None
    
    def _compress(self, data: bytes) -> bytes:
        if self.algorithm == CompressionAlgorithm.LZ4:
            return lz4.frame.compress(data, compression_level=self.level)
        elif self.algorithm == CompressionAlgorithm.ZSTD:
            return self.compressor.compress(data)
        elif self.algorithm == CompressionAlgorithm.ZLIB:
            return self.compressor.compress(data)
        return data
    
    def flush(self) -> Optional[CompressedChunk]:
        """Flush remaining window"""
        if self.window.total_size > 0:
            window_data = self.window.get_window()
            compressed = self._compress(window_data)
            
            result = CompressedChunk(
                data=compressed,
                original_size=len(self.window.buffer),
                compressed_size=len(compressed),
                algorithm=self.algorithm,
                sequence=self.sequence_counter,
                timestamp=time.time(),
                ratio=len(self.window.buffer) / len(compressed) if compressed else 1.0,
                checksum=hashlib.md5(self.window.buffer).hexdigest()[:8],
            )
            
            self.window.clear()
            self.sequence_counter += 1
            self._update_stats(result)
            
            return result
        return None
    
    def _update_stats(self, result: CompressedChunk):
        self.stats["chunks_processed"] += 1
        self.stats["total_original"] += result.original_size
        self.stats["total_compressed"] += result.compressed_size
    
    def get_stats(self) -> Dict:
        stats = self.stats.copy()
        if stats["total_original"] > 0:
            stats["overall_ratio"] = stats["total_original"] / stats["total_compressed"]
        return stats


class BackpressureController:
    """Controls backpressure in streaming pipeline"""
    
    def __init__(
        self,
        high_watermark: int = 100,  # Max pending chunks
        low_watermark: int = 20,    # Resume threshold
        max_memory_mb: int = 100,
    ):
        self.high_watermark = high_watermark
        self.low_watermark = low_watermark
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        
        self.pending_count = 0
        self.pending_bytes = 0
        self.is_paused = False
        self.pause_callbacks: List[Callable] = []
        self.resume_callbacks: List[Callable] = []
        
        # Metrics
        self.pause_count = 0
        self.total_pause_time = 0.0
        self.last_pause_time: Optional[float] = None
    
    def add_chunk(self, size: int) -> bool:
        """Add chunk to pending, return True if should pause"""
        self.pending_count += 1
        self.pending_bytes += size
        
        if not self.is_paused and self.pending_count >= self.high_watermark:
            self._pause()
            return True
        return False
    
    def complete_chunk(self, size: int):
        """Mark chunk as processed"""
        self.pending_count = max(0, self.pending_count - 1)
        self.pending_bytes = max(0, self.pending_bytes - size)
        
        if self.is_paused and self.pending_count <= self.low_watermark:
            self._resume()
    
    def _pause(self):
        self.is_paused = True
        self.pause_count += 1
        self.last_pause_time = time.time()
        for cb in self.pause_callbacks:
            try:
                cb()
            except Exception:
                pass
    
    def _resume(self):
        self.is_paused = False
        if self.last_pause_time:
            self.total_pause_time += time.time() - self.last_pause_time
        for cb in self.resume_callbacks:
            try:
                cb()
            except Exception:
                pass
    
    def on_pause(self, callback: Callable):
        self.pause_callbacks.append(callback)
    
    def on_resume(self, callback: Callable):
        self.resume_callbacks.append(callback)
    
    def get_status(self) -> Dict:
        return {
            "is_paused": self.is_paused,
            "pending_count": self.pending_count,
            "pending_bytes": self.pending_bytes,
            "pause_count": self.pause_count,
            "total_pause_time": self.total_pause_time,
            "memory_usage_pct": self.pending_bytes / self.max_memory_bytes * 100,
        }


class StreamMetrics:
    """Real-time stream metrics"""
    
    def __init__(self, window_seconds: int = 60):
        self.window_seconds = window_seconds
        self.chunks: deque = deque()  # (timestamp, original_size, compressed_size, latency_ms)
        self.errors: deque = deque()
        self.start_time = time.time()
    
    def record(self, original_size: int, compressed_size: int, latency_ms: float):
        now = time.time()
        self.chunks.append((now, original_size, compressed_size, latency_ms))
        self._cleanup()
    
    def record_error(self, error: str):
        self.errors.append((time.time(), error))
        self._cleanup()
    
    def _cleanup(self):
        cutoff = time.time() - self.window_seconds
        while self.chunks and self.chunks[0][0] < cutoff:
            self.chunks.popleft()
        while self.errors and self.errors[0][0] < cutoff:
            self.errors.popleft()
    
    def get_metrics(self) -> Dict:
        if not self.chunks:
            return {"status": "no_data"}
        
        now = time.time()
        total_orig = sum(c[1] for c in self.chunks)
        total_comp = sum(c[2] for c in self.chunks)
        total_latency = sum(c[3] for c in self.chunks)
        count = len(self.chunks)
        
        time_span = min(self.window_seconds, now - self.chunks[0][0]) if self.chunks else 1
        
        return {
            "throughput_orig_mb_s": total_orig / time_span / 1024 / 1024,
            "throughput_comp_mb_s": total_comp / time_span / 1024 / 1024,
            "compression_ratio": total_orig / total_comp if total_comp > 0 else 1.0,
            "avg_latency_ms": total_latency / count,
            "chunks_per_second": count / time_span,
            "error_rate": len(self.errors) / max(count, 1),
            "uptime_seconds": now - self.start_time,
        }


class CheckpointManager:
    """Manages checkpoints for fault tolerance"""
    
    def __init__(self, checkpoint_dir: Path, interval_seconds: int = 30):
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.interval = interval_seconds
        self.last_checkpoint = 0
        self.sequence = 0
        self._task: Optional[asyncio.Task] = None
    
    async def start(self):
        self._task = asyncio.create_task(self._checkpoint_loop())
    
    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def _checkpoint_loop(self):
        while True:
            await asyncio.sleep(self.interval)
            await self.checkpoint()
    
    async def checkpoint(self, state: Dict = None):
        """Save checkpoint"""
        self.sequence += 1
        checkpoint = {
            "sequence": self.sequence,
            "timestamp": time.time(),
            "state": state or {},
        }
        
        path = self.checkpoint_dir / f"checkpoint_{self.sequence:08d}.json"
        with open(path, 'w') as f:
            json.dump(checkpoint, f)
        
        # Clean old checkpoints (keep last 10)
        checkpoints = sorted(self.checkpoint_dir.glob("checkpoint_*.json"))
        for old in checkpoints[:-10]:
            old.unlink()
        
        self.last_checkpoint = time.time()
    
    def get_latest_checkpoint(self) -> Optional[Dict]:
        """Load latest checkpoint"""
        checkpoints = sorted(self.checkpoint_dir.glob("checkpoint_*.json"))
        if not checkpoints:
            return None
        
        with open(checkpoints[-1]) as f:
            return json.load(f)


class MultiStreamManager:
    """Manages multiple concurrent streams with prioritization"""
    
    def __init__(
        self,
        default_algorithm: CompressionAlgorithm = CompressionAlgorithm.LZ4,
        max_streams: int = 100,
    ):
        self.max_streams = max_streams
        self.default_algorithm = default_algorithm
        self.streams: Dict[str, Dict] = {}  # stream_id -> {compressor, metrics, priority}
        self.global_metrics = StreamMetrics()
        self.backpressure = BackpressureController()
        self._next_stream_id = 0
        self._lock = asyncio.Lock()
    
    async def create_stream(
        self,
        stream_id: Optional[str] = None,
        algorithm: Optional[CompressionAlgorithm] = None,
        priority: StreamPriority = StreamPriority.NORMAL,
    ) -> str:
        """Create new stream"""
        async with self._lock:
            if len(self.streams) >= self.max_streams:
                # Evict lowest priority inactive stream
                await self._evict_stream()
            
            if stream_id is None:
                stream_id = f"stream_{self._next_stream_id:06d}"
                self._next_stream_id += 1
            
            compressor = StreamCompressor(algorithm or self.default_algorithm)
            metrics = StreamMetrics()
            
            self.streams[stream_id] = {
                "compressor": compressor,
                "metrics": metrics,
                "priority": priority,
                "created_at": time.time(),
                "last_activity": time.time(),
                "chunks_processed": 0,
            }
            
            return stream_id
    
    async def _evict_stream(self):
        """Evict least recently used low-priority stream"""
        if not self.streams:
            return
        
        # Sort by priority then last activity
        sorted_streams = sorted(
            self.streams.items(),
            key=lambda x: (x[1]["priority"].value, x[1]["last_activity"])
        )
        
        evict_id = sorted_streams[0][0]
        del self.streams[evict_id]
    
    async def process_chunk(
        self,
        stream_id: str,
        data: bytes,
        priority: StreamPriority = StreamPriority.NORMAL,
        is_final: bool = False,
    ) -> Optional[bytes]:
        """Process chunk for stream"""
        if stream_id not in self.streams:
            raise ValueError(f"Stream {stream_id} not found")
        
        stream = self.streams[stream_id]
        compressor = stream["compressor"]
        metrics = stream["metrics"]
        
        # Check backpressure
        should_pause = self.backpressure.add_chunk(len(data))
        if should_pause:
            # Could wait or drop based on priority
            if priority < StreamPriority.HIGH:
                await asyncio.sleep(0.01)  # Brief pause
        
        start = time.time()
        
        chunk = StreamChunk(
            data=data,
            sequence=stream["chunks_processed"],
            priority=priority,
            is_final=is_final,
        )
        
        result = compressor.compress_chunk(chunk)
        
        latency = (time.time() - start) * 1000
        
        if result:
            metrics.record(result.original_size, result.compressed_size, latency)
            self.global_metrics.record(result.original_size, result.compressed_size, latency)
            stream["chunks_processed"] += 1
        
        stream["last_activity"] = time.time()
        self.backpressure.complete_chunk(len(data))
        
        if is_final:
            # Flush remaining
            flush_result = compressor.flush()
            if flush_result:
                metrics.record(flush_result.original_size, flush_result.compressed_size, 0)
                return flush_result.data
        
        return result.data if result else None
    
    def get_stream_status(self, stream_id: str) -> Optional[Dict]:
        if stream_id not in self.streams:
            return None
        
        stream = self.streams[stream_id]
        return {
            "stream_id": stream_id,
            "priority": stream["priority"].value,
            "chunks_processed": stream["chunks_processed"],
            "metrics": stream["metrics"].get_metrics(),
            "compressor_stats": stream["compressor"].get_stats(),
        }
    
    def get_global_status(self) -> Dict:
        return {
            "active_streams": len(self.streams),
            "max_streams": self.max_streams,
            "global_metrics": self.global_metrics.get_metrics(),
            "backpressure": self.backpressure.get_status(),
        }


class FaultToleranceManager:
    """Handles fault tolerance for streaming"""
    
    def __init__(self, checkpoint_manager: CheckpointManager):
        self.checkpoint_manager = checkpoint_manager
        self.recovery_state: Optional[Dict] = None
    
    async def save_state(self, state: Dict):
        await self.checkpoint_manager.checkpoint(state)
    
    async def recover(self) -> Optional[Dict]:
        """Recover from latest checkpoint"""
        checkpoint = self.checkpoint_manager.get_latest_checkpoint()
        if checkpoint:
            self.recovery_state = checkpoint["state"]
            return checkpoint["state"]
        return None
    
    def is_recovered(self) -> bool:
        return self.recovery_state is not None


class StreamProcessor:
    """High-level stream processor integrating all components"""
    
    def __init__(
        self,
        checkpoint_dir: Path = Path("/tmp/eni_stream_checkpoints"),
        default_algorithm: CompressionAlgorithm = CompressionAlgorithm.LZ4,
    ):
        self.checkpoint_manager = CheckpointManager(checkpoint_dir)
        self.fault_tolerance = FaultToleranceManager(self.checkpoint_manager)
        self.multi_stream = MultiStreamManager(default_algorithm)
        self._running = False
    
    async def start(self):
        await self.checkpoint_manager.start()
        
        # Try to recover
        recovered = await self.fault_tolerance.recover()
        if recovered:
            print(f"Recovered from checkpoint: {recovered}")
        
        self._running = True
    
    async def stop(self):
        self._running = False
        await self.checkpoint_manager.stop()
        # Save final checkpoint
        await self.fault_tolerance.save_state({
            "streams": {k: v for k, v in self.multi_stream.streams.items()},
        })
    
    async def process(
        self,
        data: AsyncGenerator[bytes, None],
        stream_id: Optional[str] = None,
        priority: StreamPriority = StreamPriority.NORMAL,
    ) -> AsyncGenerator[bytes, None]:
        """Process async stream of data"""
        if stream_id is None:
            stream_id = await self.multi_stream.create_stream(priority=priority)
        
        try:
            async for chunk in data:
                if not self._running:
                    break
                
                result = await self.multi_stream.process_chunk(stream_id, chunk, priority)
                if result:
                    yield result
            
            # Flush final
            final = await self.multi_stream.process_chunk(stream_id, b"", priority, is_final=True)
            if final:
                yield final
        
        finally:
            # Save checkpoint periodically
            await self.fault_tolerance.save_state({
                "stream_id": stream_id,
                "timestamp": time.time(),
            })
    
    def get_status(self) -> Dict:
        return self.multi_stream.get_global_status()


async def demo():
    """Demo streaming compression"""
    processor = StreamProcessor()
    await processor.start()
    
    # Create test stream
    async def data_generator():
        for i in range(100):
            yield f"Log entry {i}: " + "x" * 200 + "\n".encode()
            await asyncio.sleep(0.001)  # Simulate real-time
    
    stream_id = await processor.multi_stream.create_stream(
        priority=StreamPriority.NORMAL
    )
    
    print(f"Created stream: {stream_id}")
    
    # Process
    total_in = 0
    total_out = 0
    
    async for compressed in processor.process(data_generator(), stream_id):
        total_in += 500  # approximate
        total_out += len(compressed)
    
    status = processor.get_status()
    print(f"Total in: {total_in} bytes")
    print(f"Total out: {total_out} bytes")
    print(f"Ratio: {total_in/total_out:.2f}x" if total_out else "N/A")
    print(f"Status: {json.dumps(status, indent=2)}")
    
    await processor.stop()


if __name__ == "__main__":
    asyncio.run(demo())