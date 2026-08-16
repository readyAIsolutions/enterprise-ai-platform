# Session Management: TypeScript → Python Implementation

This documents the session storage, transcript handling, and background task isolation patterns from `src/utils/sessionStorage.ts` and `src/utils/transcript.ts`.

## Transcript Format (JSONL)

```python
# Each line is a complete JSON object:
{
    "uuid": "msg-uuid-v4",           # Unique message ID
    "type": "user|assistant|system|tool",  # Message type
    "message": {...},                 # Full message object
    "timestamp": "2024-01-15T10:30:00.000Z",
    "parent_uuid": "prev-msg-uuid",   # For branching/resumption
    "session_id": "session-uuid",     # Session identifier
    "version": 1                      # Format version
}

# Tool message example:
{
    "uuid": "abc-123",
    "type": "assistant",
    "message": {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "I'll check that file."},
            {"type": "tool_use", "id": "tool-1", "name": "Read", "input": {"path": "/home/user/test.py"}}
        ]
    },
    "timestamp": "2024-01-15T10:30:00.000Z",
    "parent_uuid": "prev-uuid",
    "session_id": "session-123",
    "version": 1
}
```

## Session Manager

```python
import json
import uuid
import os
import aiofiles
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass
from contextlib import asynccontextmanager

@dataclass
class SessionConfig:
    sessions_dir: Path = Path.home() / ".hermes" / "sessions"
    max_session_size: int = 50 * 1024 * 1024  # 50MB
    compression_threshold: int = 1000  # messages
    auto_compress: bool = True

class SessionManager:
    def __init__(self, config: SessionConfig = None):
        self.config = config or SessionConfig()
        self.config.sessions_dir.mkdir(parents=True, exist_ok=True)
    
    def get_session_path(self, session_id: str) -> Path:
        return self.config.sessions_dir / f"{session_id}.jsonl"
    
    def get_agent_transcript_path(self, agent_id: str) -> Path:
        return self.config.sessions_dir / f"{agent_id}.jsonl"
    
    async def create_session(self, parent_session_id: Optional[str] = None) -> str:
        session_id = str(uuid.uuid4())
        path = self.get_session_path(session_id)
        
        # Write initial system message
        initial_msg = {
            "uuid": str(uuid.uuid4()),
            "type": "system",
            "message": {"role": "system", "content": "Session started"},
            "timestamp": datetime.now().isoformat() + "Z",
            "parent_uuid": None,
            "session_id": session_id,
            "version": 1
        }
        
        async with aiofiles.open(path, 'w') as f:
            await f.write(json.dumps(initial_msg) + '\n')
        
        # If resuming from parent, copy relevant history
        if parent_session_id:
            await self._copy_session_history(parent_session_id, session_id)
        
        return session_id
    
    async def append_message(self, session_id: str, message: Dict[str, Any]):
        """Append a message to session transcript."""
        path = self.get_session_path(session_id)
        
        # Ensure required fields
        if 'uuid' not in message:
            message['uuid'] = str(uuid.uuid4())
        if 'timestamp' not in message:
            message['timestamp'] = datetime.now().isoformat() + 'Z'
        if 'session_id' not in message:
            message['session_id'] = session_id
        if 'version' not in message:
            message['version'] = 1
        
        async with aiofiles.open(path, 'a') as f:
            await f.write(json.dumps(message) + '\n')
        
        # Check if compression needed
        if self.config.auto_compress:
            await self._maybe_compress(session_id)
    
    async def append_messages_batch(self, session_id: str, messages: List[Dict]):
        """Efficiently append multiple messages."""
        path = self.get_session_path(session_id)
        
        lines = []
        for msg in messages:
            if 'uuid' not in msg:
                msg['uuid'] = str(uuid.uuid4())
            if 'timestamp' not in msg:
                msg['timestamp'] = datetime.now().isoformat() + 'Z'
            if 'session_id' not in msg:
                msg['session_id'] = session_id
            if 'version' not in msg:
                msg['version'] = 1
            lines.append(json.dumps(msg))
        
        async with aiofiles.open(path, 'a') as f:
            await f.write('\n'.join(lines) + '\n')
    
    async def load_session(self, session_id: str) -> List[Dict]:
        """Load all messages from a session."""
        path = self.get_session_path(session_id)
        if not path.exists():
            return []
        
        messages = []
        async with aiofiles.open(path, 'r') as f:
            async for line in f:
                line = line.strip()
                if line:
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return messages
    
    async def get_last_n_messages(self, session_id: str, n: int) -> List[Dict]:
        """Efficiently get last N messages without loading entire file."""
        path = self.get_session_path(session_id)
        if not path.exists():
            return []
        
        # Read last N lines using tail-like approach
        messages = []
        async with aiofiles.open(path, 'r') as f:
            # Seek to end and read backwards
            await f.seek(0, os.SEEK_END)
            file_size = await f.tell()
            
            buffer = ""
            lines_found = 0
            chunk_size = 8192
            
            while lines_found < n and file_size > 0:
                read_size = min(chunk_size, file_size)
                file_size -= read_size
                await f.seek(file_size)
                chunk = await f.read(read_size)
                buffer = chunk + buffer
                lines = buffer.split('\n')
                buffer = lines[0]  # Incomplete line at start
                for line in reversed(lines[1:]):
                    if line.strip():
                        try:
                            messages.append(json.loads(line))
                            lines_found += 1
                            if lines_found >= n:
                                break
                        except json.JSONDecodeError:
                            pass
        
        return list(reversed(messages))
    
    async def _maybe_compress(self, session_id: str):
        """Compress session if it exceeds threshold."""
        path = self.get_session_path(session_id)
        if not path.exists():
            return
        
        # Count messages
        count = 0
        async with aiofiles.open(path, 'r') as f:
            async for _ in f:
                count += 1
        
        if count > self.config.compression_threshold:
            await self.compress_session(session_id)
    
    async def compress_session(self, session_id: str, keep_last: int = 50) -> str:
        """Compress old messages into a summary."""
        messages = await self.load_session(session_id)
        if len(messages) <= keep_last:
            return session_id
        
        # Create summary of old messages
        old_messages = messages[:-keep_last]
        recent_messages = messages[-keep_last:]
        
        summary = await self._generate_summary(old_messages)
        
        # Create new session with summary + recent
        new_session_id = str(uuid.uuid4())
        new_path = self.get_session_path(new_session_id)
        
        async with aiofiles.open(new_path, 'w') as f:
            # System message with summary
            await f.write(json.dumps({
                "uuid": str(uuid.uuid4()),
                "type": "system",
                "message": {
                    "role": "system",
                    "content": f"Previous context summary: {summary}"
                },
                "timestamp": datetime.now().isoformat() + "Z",
                "parent_uuid": None,
                "session_id": new_session_id,
                "version": 1
            }) + '\n')
            
            # Recent messages
            for msg in recent_messages:
                msg['session_id'] = new_session_id
                await f.write(json.dumps(msg) + '\n')
        
        # Keep original as backup
        backup_path = self.config.sessions_dir / f"{session_id}.jsonl.backup"
        os.rename(path, backup_path)
        
        return new_session_id
    
    async def _generate_summary(self, messages: List[Dict]) -> str:
        """Generate summary of messages (would call LLM in practice)."""
        # In real implementation, call LLM to summarize
        tool_count = sum(1 for m in messages if m.get('type') == 'tool')
        user_count = sum(1 for m in messages if m.get('type') == 'user')
        assistant_count = sum(1 for m in messages if m.get('type') == 'assistant')
        
        return f"Session had {len(messages)} messages: {user_count} user, {assistant_count} assistant, {tool_count} tool calls."


# =============================================================================
# Sidechain Transcripts (Background Tasks)
# =============================================================================

class SidechainManager:
    """Manages isolated transcripts for background agents/tasks."""
    
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self.sidechains: Dict[str, Path] = {}
    
    def create_sidechain(self, parent_session_id: str, agent_id: str) -> Path:
        """Create isolated transcript for subagent/task."""
        sidechain_path = self.session_manager.config.sessions_dir / f"{agent_id}.jsonl"
        
        # Symlink to parent for /clear handling
        parent_path = self.session_manager.get_session_path(parent_session_id)
        if parent_path.exists() and not sidechain_path.exists():
            os.symlink(parent_path, sidechain_path)
        
        self.sidechains[agent_id] = sidechain_path
        return sidechain_path
    
    async def append_to_sidechain(self, agent_id: str, message: Dict):
        """Append message to sidechain transcript."""
        path = self.sidechains.get(agent_id)
        if not path:
            return
        
        if 'session_id' not in message:
            message['session_id'] = agent_id
        
        async with aiofiles.open(path, 'a') as f:
            await f.write(json.dumps(message) + '\n')
    
    def re_link_after_clear(self, agent_id: str, new_parent_session_id: str):
        """After /clear, re-link sidechain to new parent session."""
        path = self.sidechains.get(agent_id)
        if path and path.is_symlink():
            os.unlink(path)
            new_parent = self.session_manager.get_session_path(new_parent_session_id)
            os.symlink(new_parent, path)


# =============================================================================
# Session Resumption
# =============================================================================

class SessionResumption:
    """Handle --continue, --resume, -c flags."""
    
    def __init__(self, session_manager: SessionManager):
        self.sm = session_manager
    
    async def resolve_session(self, specifier: Optional[str]) -> Optional[str]:
        """Resolve session by ID, name, or 'latest'."""
        if not specifier:
            return await self._get_latest_session()
        
        if specifier == "latest" or specifier is True:
            return await self._get_latest_session()
        
        # Try as UUID
        if self._is_valid_uuid(specifier):
            if await self.sm.session_exists(specifier):
                return specifier
        
        # Try as title/name
        return await self._find_session_by_title(specifier)
    
    async def _get_latest_session(self) -> Optional[str]:
        """Get most recent session ID."""
        sessions = []
        for path in self.sm.config.sessions_dir.glob("*.jsonl"):
            if path.name.endswith(('.backup', '.jsonl.backup')):
                continue
            try:
                stat = path.stat()
                # Read first message to get session_id
                async with aiofiles.open(path, 'r') as f:
                    first_line = await f.readline()
                    if first_line:
                        msg = json.loads(first_line)
                        sessions.append((stat.st_mtime, msg.get('session_id')))
            except Exception:
                pass
        
        if sessions:
            sessions.sort(reverse=True)
            return sessions[0][1]
        return None
    
    async def _find_session_by_title(self, title: str) -> Optional[str]:
        """Find session by first user message content."""
        for path in self.sm.config.sessions_dir.glob("*.jsonl"):
            if path.name.endswith(('.backup', '.jsonl.backup')):
                continue
            try:
                async with aiofiles.open(path, 'r') as f:
                    async for line in f:
                        msg = json.loads(line)
                        if msg.get('type') == 'user':
                            content = msg.get('message', {}).get('content', '')
                            if title.lower() in str(content).lower():
                                return msg.get('session_id')
                            break
            except Exception:
                pass
        return None


# =============================================================================
# Usage in Agent
# =============================================================================

class Agent:
    def __init__(self):
        self.session_manager = SessionManager()
        self.sidechain_manager = SidechainManager(self.session_manager)
        self.resumption = SessionResumption(self.session_manager)
        self.current_session_id: Optional[str] = None
    
    async def start_session(self, resume: Optional[str] = None, continue_last: bool = False):
        if resume or continue_last:
            self.current_session_id = await self.resumption.resolve_session(
                resume if resume else "latest"
            )
            if not self.current_session_id:
                raise ValueError("No session found to resume")
            
            # Load history
            messages = await self.session_manager.load_session(self.current_session_id)
            return messages
        else:
            # New session
            self.current_session_id = await self.session_manager.create_session()
            return []
    
    async def add_message(self, message: Dict):
        if not self.current_session_id:
            raise RuntimeError("No active session")
        await self.session_manager.append_message(self.current_session_id, message)
    
    async def start_background_task(self, prompt: str, description: str) -> str:
        """Start background task with isolated transcript."""
        task_id = str(uuid.uuid4())[:8]
        sidechain_path = self.sidechain_manager.create_sidechain(
            self.current_session_id, task_id
        )
        
        # Run in background
        asyncio.create_task(self._run_background_task(task_id, sidechain_path, prompt))
        
        return task_id
    
    async def _run_background_task(self, task_id: str, path: Path, prompt: str):
        # Implementation similar to LocalMainSessionTask.ts
        pass


# =============================================================================
# Session Lifecycle Commands
# =============================================================================

# CLI commands mapped to operations:
SESSION_COMMANDS = {
    "sessions list": "List all sessions with metadata",
    "sessions browse": "Interactive session picker",
    "sessions rename <id> <title>": "Rename/title a session",
    "sessions delete <id>": "Delete a session",
    "sessions compress <id>": "Compress old messages in session",
    "hermes -c": "Continue last session",
    "hermes -c 'name'": "Continue session by name",
    "hermes --resume <id>": "Resume specific session",
    "hermes -z 'prompt'": "One-shot mode (no session)",
}