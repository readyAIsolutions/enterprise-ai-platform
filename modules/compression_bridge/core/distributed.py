#!/usr/bin/env python3
"""
Distributed Multi-Node Swarm with Gossip Protocol
==================================================
Workers across machines with gossip-based coordination.
"""
import asyncio
import json
import hashlib
import time
import ssl
import secrets
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import deque
import socket
import uuid


class NodeRole(Enum):
    WORKER = "worker"
    COORDINATOR = "coordinator"
    LEADER = "leader"


class MessageType(Enum):
    GOSSIP = "gossip"
    HEARTBEAT = "heartbeat"
    TASK_SUBMIT = "task_submit"
    TASK_RESULT = "task_result"
    TASK_STEAL = "task_steal"
    LEADER_ELECTION = "leader_election"
    NODE_JOIN = "node_join"
    NODE_LEAVE = "node_leave"
    SYNC_REQUEST = "sync_request"
    SYNC_RESPONSE = "sync_response"
    CONFIG_UPDATE = "config_update"


@dataclass
class NodeInfo:
    node_id: str
    address: str  # host:port
    role: NodeRole
    capabilities: List[str] = field(default_factory=list)
    last_seen: float = field(default_factory=time.time)
    load: float = 0.0
    tasks_completed: int = 0
    tasks_failed: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    public_key: Optional[str] = None  # For mTLS
    
    def is_alive(self, timeout: float = 30.0) -> bool:
        return time.time() - self.last_seen < timeout
    
    def to_dict(self) -> Dict:
        return {
            "node_id": self.node_id,
            "address": self.address,
            "role": self.role.value,
            "capabilities": self.capabilities,
            "last_seen": self.last_seen,
            "load": self.load,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "metadata": self.metadata,
        }


@dataclass
class GossipMessage:
    message_type: MessageType
    sender_id: str
    timestamp: float
    payload: Dict[str, Any]
    ttl: int = 3  # Time to live for gossip propagation
    message_id: str = field(default_factory=lambda: hashlib.sha256(f"{time.time()}{secrets.token_hex(8)}".encode()).hexdigest()[:12])
    
    def to_bytes(self) -> bytes:
        return json.dumps({
            "type": self.message_type.value,
            "sender": self.sender_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "ttl": self.ttl,
            "msg_id": self.message_id,
        }).encode()
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'GossipMessage':
        obj = json.loads(data.decode())
        return cls(
            message_type=MessageType(obj["type"]),
            sender_id=obj["sender"],
            timestamp=obj["timestamp"],
            payload=obj["payload"],
            ttl=obj.get("ttl", 3),
            message_id=obj.get("msg_id", ""),
        )


class GossipProtocol:
    """Gossip-based cluster membership and state dissemination"""
    
    def __init__(
        self,
        node_id: str,
        address: str,
        peer_addresses: List[str],
        fanout: int = 3,
        interval: float = 1.0,
        suspicion_threshold: float = 5.0,
    ):
        self.node_id = node_id
        self.address = address
        self.peer_addresses = set(peer_addresses)
        self.fanout = fanout
        self.interval = interval
        self.suspicion_threshold = suspicion_threshold
        
        # Cluster state
        self.members: Dict[str, NodeInfo] = {}
        self.suspects: Dict[str, float] = {}  # node_id -> suspicion_time
        self.message_history: Set[str] = set()  # For deduplication
        self.max_history = 10000
        
        # Network
        self.server: Optional[asyncio.Server] = None
        self.connections: Dict[str, asyncio.StreamWriter] = {}
        self._running = False
        self._tasks: List[asyncio.Task] = []
        
        # Callbacks
        self.on_member_join: Optional[Callable[[NodeInfo], None]] = None
        self.on_member_leave: Optional[Callable[[str], None]] = None
        self.on_message: Optional[Callable[[GossipMessage], None]] = None
    
    async def start(self):
        """Start gossip protocol"""
        self._running = True
        
        # Start TCP server
        host, port = self.address.split(":")
        self.server = await asyncio.start_server(
            self._handle_connection, host, int(port)
        )
        
        # Connect to peers
        await self._connect_to_peers()
        
        # Start gossip loop
        self._tasks.append(asyncio.create_task(self._gossip_loop()))
        self._tasks.append(asyncio.create_task(self._suspicion_loop()))
        self._tasks.append(asyncio.create_task(self._cleanup_loop()))
        
        # Register self
        self._register_self()
    
    async def stop(self):
        """Stop gossip protocol"""
        self._running = False
        
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        
        for writer in self.connections.values():
            writer.close()
            await writer.wait_closed()
    
    def _register_self(self):
        """Register this node in local membership"""
        host, port = self.address.split(":")
        self_info = NodeInfo(
            node_id=self.node_id,
            address=self.address,
            role=NodeRole.WORKER,
            capabilities=["compression", "wenyan", "pxpipe", "glyph"],
            load=0.0,
        )
        self.members[self.node_id] = self_info
    
    async def _connect_to_peers(self):
        """Connect to known peers"""
        for peer_addr in self.peer_addresses:
            if peer_addr == self.address:
                continue
            try:
                host, port = peer_addr.split(":")
                reader, writer = await asyncio.open_connection(host, int(port))
                self.connections[peer_addr] = writer
                # Send join message
                await self._send_message(peer_addr, GossipMessage(
                    message_type=MessageType.NODE_JOIN,
                    sender_id=self.node_id,
                    timestamp=time.time(),
                    payload={"node_info": self.members[self.node_id].to_dict()}
                ))
            except Exception:
                pass  # Will retry via gossip
    
    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming connection"""
        peer_addr = writer.get_extra_info("peername")
        peer_key = f"{peer_addr[0]}:{peer_addr[1]}"
        self.connections[peer_key] = writer
        
        try:
            while self._running:
                data = await reader.read(8192)
                if not data:
                    break
                
                try:
                    msg = GossipMessage.from_bytes(data)
                    await self._process_message(msg, writer)
                except Exception as e:
                    pass  # Invalid message
        except Exception:
            pass
        finally:
            writer.close()
            await writer.wait_closed()
            self.connections.pop(peer_key, None)
    
    async def _process_message(self, msg: GossipMessage, writer: asyncio.StreamWriter):
        """Process incoming gossip message"""
        # Deduplication
        if msg.message_id in self.message_history:
            return
        
        self.message_history.add(msg.message_id)
        if len(self.message_history) > self.max_history:
            self.message_history = set(list(self.message_history)[-self.max_history:])
        
        # Update sender info
        if msg.sender_id != self.node_id:
            if msg.sender_id in self.suspects:
                del self.suspects[msg.sender_id]
            
            if msg.message_type == MessageType.NODE_JOIN:
                node_info = NodeInfo(**msg.payload["node_info"])
                if node_info.node_id not in self.members:
                    self.members[node_info.node_id] = node_info
                    if self.on_member_join:
                        self.on_member_join(node_info)
            
            elif msg.message_type == MessageType.NODE_LEAVE:
                if msg.payload.get("node_id") in self.members:
                    left_id = msg.payload["node_id"]
                    del self.members[left_id]
                    if self.on_member_leave:
                        self.on_member_leave(left_id)
            
            elif msg.message_type == MessageType.GOSSIP:
                # Merge membership
                for node_data in msg.payload.get("members", []):
                    node_id = node_data["node_id"]
                    if node_id != self.node_id and node_id not in self.members:
                        self.members[node_id] = NodeInfo(**node_data)
        
        # Decrement TTL and forward
        if msg.ttl > 0:
            msg.ttl -= 1
            await self._gossip_to_peers(msg)
        
        # Callback
        if self.on_message:
            self.on_message(msg)
    
    async def _gossip_loop(self):
        """Main gossip loop"""
        while self._running:
            await asyncio.sleep(self.interval)
            await self._gossip_state()
    
    async def _gossip_state(self):
        """Gossip current state to random peers"""
        # Prepare gossip message
        msg = GossipMessage(
            message_type=MessageType.GOSSIP,
            sender_id=self.node_id,
            timestamp=time.time(),
            payload={
                "members": [m.to_dict() for m in self.members.values()],
                "sender_load": self.members.get(self.node_id, NodeInfo("", "", NodeRole.WORKER)).load,
            }
        )
        await self._gossip_to_peers(msg)
    
    async def _gossip_to_peers(self, msg: GossipMessage):
        """Send message to random subset of peers"""
        peers = list(self.connections.keys())
        if not peers:
            return
        
        targets = random.sample(peers, min(self.fanout, len(peers)))
        for peer in targets:
            try:
                writer = self.connections[peer]
                writer.write(msg.to_bytes() + b"\n")
                await writer.drain()
            except Exception:
                # Connection failed, will be cleaned up
                pass
    
    async def _suspicion_loop(self):
        """Detect failed nodes"""
        while self._running:
            await asyncio.sleep(1.0)
            now = time.time()
            
            for node_id, member in list(self.members.items()):
                if node_id == self.node_id:
                    continue
                
                if now - member.last_seen > self.suspicion_threshold:
                    if node_id not in self.suspects:
                        self.suspects[node_id] = now
                    elif now - self.suspects[node_id] > self.suspicion_threshold * 2:
                        # Confirm dead
                        self._mark_dead(node_id)
    
    def _mark_dead(self, node_id: str):
        """Mark node as dead"""
        if node_id in self.members:
            del self.members[node_id]
            if self.on_member_leave:
                self.on_member_leave(node_id)
        self.suspects.pop(node_id, None)
    
    async def _cleanup_loop(self):
        """Cleanup old message history"""
        while self._running:
            await asyncio.sleep(60.0)
            if len(self.message_history) > self.max_history:
                self.message_history = set(list(self.message_history)[-self.max_history:])
    
    async def _send_message(self, target: str, msg: GossipMessage):
        """Send message to specific target"""
        if target in self.connections:
            writer = self.connections[target]
            writer.write(msg.to_bytes() + b"\n")
            await writer.drain()
    
    def broadcast(self, msg_type: MessageType, payload: Dict):
        """Broadcast message to cluster"""
        msg = GossipMessage(
            message_type=msg_type,
            sender_id=self.node_id,
            timestamp=time.time(),
            payload=payload
        )
        asyncio.create_task(self._gossip_to_peers(msg))
    
    def get_cluster_view(self) -> List[NodeInfo]:
        """Get current cluster view"""
        return list(self.members.values())


class DistributedTaskQueue:
    """Distributed task queue with work stealing"""
    
    def __init__(self, gossip: GossipProtocol, node_id: str):
        self.gossip = gossip
        self.node_id = node_id
        self.local_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.pending: Dict[str, Dict] = {}  # task_id -> task
        self.processing: Dict[str, Dict] = {}
        self.completed: Dict[str, Any] = {}
        
        # Work stealing
        self.steal_interval = 5.0
        self._steal_task: Optional[asyncio.Task] = None
        
        # Register message handler
        gossip.on_message = self._handle_gossip_message
    
    async def start(self):
        self._steal_task = asyncio.create_task(self._steal_loop())
    
    async def stop(self):
        if self._steal_task:
            self._steal_task.cancel()
            try:
                await self._steal_task
            except asyncio.CancelledError:
                pass
    
    async def submit(self, task: Dict, priority: int = 0) -> str:
        """Submit task to queue"""
        task_id = hashlib.sha256(f"{time.time()}{json.dumps(task, sort_keys=True)}".encode()).hexdigest()[:12]
        
        task_entry = {
            "task_id": task_id,
            "task": task,
            "priority": priority,
            "submitter": self.node_id,
            "created_at": time.time(),
            "assigned_to": None,
            "status": "queued",
        }
        
        await self.local_queue.put((priority, task_id, task_entry))
        self.pending[task_id] = task_entry
        
        # Broadcast to cluster for work stealing visibility
        self.gossip.broadcast(MessageType.TASK_SUBMIT, {
            "task_id": task_id,
            "priority": priority,
            "submitter": self.node_id,
        })
        
        return task_id
    
    async def get_task(self) -> Optional[Dict]:
        """Get next task (local or stolen)"""
        try:
            priority, task_id, task_entry = await asyncio.wait_for(
                self.local_queue.get(), timeout=1.0
            )
            task_entry["status"] = "processing"
            task_entry["assigned_to"] = self.node_id
            self.processing[task_id] = task_entry
            return task_entry
        except asyncio.TimeoutError:
            return None
    
    async def complete_task(self, task_id: str, result: Any):
        """Mark task as completed"""
        if task_id in self.processing:
            task_entry = self.processing.pop(task_id)
            task_entry["status"] = "completed"
            task_entry["result"] = result
            task_entry["completed_at"] = time.time()
            self.completed[task_id] = task_entry
            
            # Broadcast result
            self.gossip.broadcast(MessageType.TASK_RESULT, {
                "task_id": task_id,
                "result": result,
                "completed_by": self.node_id,
            })
    
    async def fail_task(self, task_id: str, error: str):
        """Mark task as failed"""
        if task_id in self.processing:
            task_entry = self.processing.pop(task_id)
            task_entry["status"] = "failed"
            task_entry["error"] = error
            
            # Re-queue with incremented retry
            task_entry["retry_count"] = task_entry.get("retry_count", 0) + 1
            if task_entry["retry_count"] < 3:
                await self.submit(task_entry["task"], task_entry["priority"])
    
    async def _steal_loop(self):
        """Periodically steal work from busy peers"""
        while True:
            await asyncio.sleep(self.steal_interval)
            
            # Check if we have capacity
            cluster = self.gossip.get_cluster_view()
            my_load = sum(1 for t in self.processing.values())
            
            # Find busy peers
            busy_peers = [
                n for n in cluster 
                if n.node_id != self.node_id and n.load > my_load + 2
            ]
            
            if busy_peers and self.local_queue.empty():
                # Request work steal
                target = random.choice(busy_peers)
                self.gossip.broadcast(MessageType.TASK_STEAL, {
                    "requester": self.node_id,
                    "target": target.node_id,
                })
    
    def _handle_gossip_message(self, msg: GossipMessage):
        """Handle task-related gossip messages"""
        if msg.message_type == MessageType.TASK_STEAL:
            if msg.payload.get("target") == self.node_id and msg.payload.get("requester") != self.node_id:
                asyncio.create_task(self._handle_steal_request(msg.payload["requester"]))
        
        elif msg.message_type == MessageType.TASK_RESULT:
            # Cache result locally
            self.completed[msg.payload["task_id"]] = msg.payload["result"]
    
    async def _handle_steal_request(self, requester: str):
        """Handle work steal request"""
        if not self.local_queue.empty():
            # Give half our queue
            stolen = []
            for _ in range(min(self.local_queue.qsize() // 2, 5)):
                try:
                    item = self.local_queue.get_nowait()
                    stolen.append(item)
                except asyncio.QueueEmpty:
                    break
            
            if stolen:
                # Send stolen tasks to requester
                self.gossip.broadcast(MessageType.TASK_SUBMIT, {
                    "tasks": [{"task_id": t[1], "task": t[2]["task"], "priority": t[0]} for t in stolen],
                    "stolen_from": self.node_id,
                    "stolen_by": requester,
                })


class LeaderElection:
    """Raft-style leader election for coordinator selection"""
    
    def __init__(self, gossip: GossipProtocol, node_id: str):
        self.gossip = gossip
        self.node_id = node_id
        self.current_term = 0
        self.voted_for: Optional[str] = None
        self.votes_received: Set[str] = set()
        self.is_leader = False
        self.leader_id: Optional[str] = None
        self.election_timeout = random.uniform(5.0, 10.0)
        self.last_heartbeat = time.time()
        self._election_task: Optional[asyncio.Task] = None
    
    async def start(self):
        self._election_task = asyncio.create_task(self._election_loop())
    
    async def stop(self):
        if self._election_task:
            self._election_task.cancel()
            try:
                await self._election_task
            except asyncio.CancelledError:
                pass
    
    async def _election_loop(self):
        while True:
            await asyncio.sleep(0.5)
            
            if self.is_leader:
                # Send heartbeats
                self.gossip.broadcast(MessageType.LEADER_ELECTION, {
                    "type": "heartbeat",
                    "term": self.current_term,
                    "leader": self.node_id,
                })
                self.last_heartbeat = time.time()
                await asyncio.sleep(1.0)
            else:
                # Check for leader heartbeat
                if time.time() - self.last_heartbeat > self.election_timeout:
                    await self._start_election()
    
    async def _start_election(self):
        self.current_term += 1
        self.voted_for = self.node_id
        self.votes_received = {self.node_id}
        
        # Request votes
        self.gossip.broadcast(MessageType.LEADER_ELECTION, {
            "type": "request_vote",
            "term": self.current_term,
            "candidate": self.node_id,
        })
        
        # Wait for votes
        await asyncio.sleep(2.0)
        
        cluster_size = len(self.gossip.get_cluster_view())
        if len(self.votes_received) > cluster_size // 2:
            self._become_leader()
    
    def _become_leader(self):
        self.is_leader = True
        self.leader_id = self.node_id
        print(f"Node {self.node_id} became leader for term {self.current_term}")
    
    def handle_vote_request(self, msg: Dict):
        """Handle incoming vote request"""
        candidate = msg["candidate"]
        term = msg["term"]
        
        if term > self.current_term:
            self.current_term = term
            self.voted_for = None
            self.is_leader = False
        
        if self.voted_for is None or self.voted_for == candidate:
            self.voted_for = candidate
            # Send vote
            self.gossip.broadcast(MessageType.LEADER_ELECTION, {
                "type": "vote",
                "term": term,
                "voter": self.node_id,
                "candidate": candidate,
            })
    
    def handle_vote(self, msg: Dict):
        """Handle vote response"""
        if msg["candidate"] == self.node_id and msg["term"] == self.current_term:
            self.votes_received.add(msg["voter"])


class DistributedSwarm:
    """Complete distributed swarm integrating gossip, tasks, and leader election"""
    
    def __init__(self, node_id: str, address: str, peer_addresses: List[str]):
        self.node_id = node_id
        self.address = address
        self.peer_addresses = peer_addresses
        
        self.gossip = GossipProtocol(node_id, address, peer_addresses)
        self.task_queue = DistributedTaskQueue(self.gossip, node_id)
        self.leader_election = LeaderElection(self.gossip, node_id)
        
        self._running = False
    
    async def start(self):
        self._running = True
        await self.gossip.start()
        await self.task_queue.start()
        await self.leader_election.start()
    
    async def stop(self):
        self._running = False
        await self.leader_election.stop()
        await self.task_queue.stop()
        await self.gossip.stop()
    
    async def submit_task(self, task: Dict, priority: int = 0) -> str:
        return await self.task_queue.submit(task, priority)
    
    def is_leader(self) -> bool:
        return self.leader_election.is_leader
    
    def get_cluster_status(self) -> Dict:
        return {
            "node_id": self.node_id,
            "is_leader": self.is_leader(),
            "leader_id": self.leader_election.leader_id,
            "cluster_size": len(self.gossip.members),
            "members": [m.to_dict() for m in self.gossip.get_cluster_view()],
            "local_queue_size": self.task_queue.local_queue.qsize(),
            "processing": len(self.task_queue.processing),
        }


# Secure transport with mTLS
def create_ssl_context(cert_path: str, key_path: str, ca_path: str) -> ssl.SSLContext:
    """Create SSL context for mTLS"""
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(cert_path, key_path)
    context.load_verify_locations(ca_path)
    context.verify_mode = ssl.CERT_REQUIRED
    return context


async def demo():
    """Demo with single node (for testing)"""
    node_id = f"node-{uuid.uuid4().hex[:8]}"
    address = "127.0.0.1:8930"
    
    swarm = DistributedSwarm(node_id, address, [])
    await swarm.start()
    
    print(f"Started node {node_id}")
    print(f"Cluster status: {swarm.get_cluster_status()}")
    
    # Submit some tasks
    for i in range(5):
        task_id = await swarm.submit_task({
            "type": "compress",
            "data": f"test data {i}".encode(),
            "mode": "balanced"
        }, priority=i)
        print(f"Submitted task {task_id}")
    
    await asyncio.sleep(2)
    print(f"Cluster status: {swarm.get_cluster_status()}")
    
    await swarm.stop()


if __name__ == "__main__":
    asyncio.run(demo())