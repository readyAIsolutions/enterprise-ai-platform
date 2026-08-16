#!/usr/bin/env python3
"""
Smart Context Management - Intelligent compression that preserves what matters
Better than Claude Code's simple truncation
"""

import asyncio
import json
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from collections import defaultdict
import hashlib


@dataclass
class MessageScore:
    """Scored message for compression decisions."""
    index: int
    message: Dict
    score: float
    category: str  # "critical", "important", "context", "noise"
    reason: str


class SmartContextManager:
    """
    Intelligent context compression that preserves what matters.
    
    Unlike simple truncation, this:
    1. Scores messages by relevance to current task
    2. Preserves: recent, tool results, decisions, errors, code
    3. Summarizes: exploration, failed attempts, context setting
    4. Drops: pure chatter, redundant confirmations, greetings
    """
    
    def __init__(self, 
                 max_tokens: int = 100000,
                 preserve_recent: int = 20,
                 compression_threshold: float = 0.8):
        self.max_tokens = max_tokens
        self.preserve_recent = preserve_recent
        self.compression_threshold = compression_threshold
        
        # Keywords that indicate importance
        self.critical_keywords = [
            "error", "exception", "traceback", "failed", "failure",
            "bug", "fix", "patch", "security", "vulnerability",
            "decision", "decided", "chosen", "selected", "approach",
            "architecture", "design", "pattern", "refactor",
            "deploy", "release", "production", "critical"
        ]
        
        self.important_keywords = [
            "function", "class", "method", "api", "endpoint",
            "database", "query", "schema", "migration",
            "test", "pytest", "jest", "coverage",
            "config", "setting", "parameter", "option",
            "import", "export", "module", "package"
        ]
        
        self.noise_keywords = [
            "thanks", "thank you", "sure", "okay", "ok",
            "great", "awesome", "perfect", "exactly",
            "understood", "got it", "makes sense",
            "let me", "i'll", "i will", "going to"
        ]
    
    def estimate_tokens(self, text: str) -> int:
        """Rough token estimation."""
        return len(text.split()) * 1.3  # Rough approximation
    
    def score_message(self, msg: Dict, current_task: str = "") -> MessageScore:
        """Score a message for preservation priority."""
        content = self._extract_text(msg)
        msg_type = msg.get("type", "unknown")
        role = msg.get("message", {}).get("role", "") if isinstance(msg.get("message"), dict) else ""
        
        score = 0.0
        category = "context"
        reasons = []
        
        # Base score by type
        if msg_type == "tool":
            score += 0.8
            category = "critical"
            reasons.append("tool_execution")
        elif msg_type == "assistant" and role == "assistant":
            if any(kw in content.lower() for kw in self.critical_keywords):
                score += 0.7
                category = "critical"
                reasons.append("critical_keyword")
            elif any(kw in content.lower() for kw in self.important_keywords):
                score += 0.5
                category = "important"
                reasons.append("important_keyword")
            elif any(kw in content.lower() for kw in self.noise_keywords):
                score -= 0.3
                category = "noise"
                reasons.append("noise_keyword")
        elif msg_type == "user":
            score += 0.6
            category = "important"
            reasons.append("user_input")
        elif msg_type == "system":
            score += 0.4
            reasons.append("system_message")
        
        # Boost for code blocks
        if "```" in content or "`" in content:
            score += 0.3
            reasons.append("has_code")
        
        # Boost for long substantive content
        if len(content) > 500:
            score += 0.2
            reasons.append("substantive")
        
        # Task relevance
        if current_task and current_task.lower() in content.lower():
            score += 0.4
            reasons.append("task_relevant")
        
        # Cap score
        score = max(-1.0, min(1.0, score))
        
        return MessageScore(
            index=-1,  # Set by caller
            message=msg,
            score=score,
            category=category,
            reason=", ".join(reasons)
        )
    
    def _extract_text(self, msg: Dict) -> str:
        """Extract text content from message."""
        if "message" in msg and isinstance(msg["message"], dict):
            content = msg["message"].get("content", "")
            if isinstance(content, list):
                return " ".join(
                    block.get("text", "") for block in content 
                    if block.get("type") == "text"
                )
            return str(content)
        return str(msg.get("content", ""))
    
    async def compress(self, 
                       messages: List[Dict], 
                       current_task: str = "",
                       target_tokens: int = None) -> Tuple[List[Dict], Dict]:
        """
        Compress messages intelligently.
        
        Returns: (compressed_messages, stats)
        """
        target = target_tokens or int(self.max_tokens * 0.7)
        current_tokens = sum(self.estimate_tokens(self._extract_text(m)) for m in messages)
        
        if current_tokens <= target:
            return messages, {"compressed": False, "original_tokens": current_tokens, "final_tokens": current_tokens}
        
        # Score all messages
        scored = []
        for i, msg in enumerate(messages):
            scored_msg = self.score_message(msg, current_task)
            scored_msg.index = i
            scored.append(scored_msg)
        
        # Always preserve recent messages
        preserve_count = min(self.preserve_recent, len(messages))
        recent_indices = set(range(len(messages) - preserve_count, len(messages)))
        
        # Separate by category
        critical = [s for s in scored if s.category == "critical"]
        important = [s for s in scored if s.category == "important"]
        context = [s for s in scored if s.category == "context"]
        noise = [s for s in scored if s.category == "noise"]
        
        # Build preserved set
        preserved = set()
        
        # Always preserve critical
        for s in critical:
            preserved.add(s.index)
        
        # Preserve important messages within token budget
        # Sort important by score descending, add until budget exhausted
        remaining_budget = target
        for s in critical:
            msg_tokens = self.estimate_tokens(self._extract_text(s.message))
            remaining_budget -= msg_tokens
        
        for s in sorted(important, key=lambda x: x.score, reverse=True):
            if s.index not in preserved:
                msg_tokens = self.estimate_tokens(self._extract_text(s.message))
                if remaining_budget >= msg_tokens:
                    preserved.add(s.index)
                    remaining_budget -= msg_tokens
                else:
                    break  # No more budget for important messages
        
        # Add recent messages
        preserved.update(recent_indices)
        
        # Add context messages by score until token budget
        for s in sorted(context, key=lambda x: x.score, reverse=True):
            if remaining_budget <= 0:
                break
            msg_tokens = self.estimate_tokens(self._extract_text(s.message))
            if remaining_budget >= msg_tokens and s.index not in preserved:
                preserved.add(s.index)
                remaining_budget -= msg_tokens
        
        # Build compressed list
        compressed = []
        summary_messages = []
        
        for i, msg in enumerate(messages):
            if i in preserved:
                compressed.append(msg)
            else:
                summary_messages.append(msg)
        
        # Create summary message for dropped content
        if summary_messages:
            summary = await self._create_summary(summary_messages, current_task)
            compressed.insert(0, summary)
        
        final_tokens = sum(self.estimate_tokens(self._extract_text(m)) for m in compressed)
        
        stats = {
            "compressed": True,
            "original_count": len(messages),
            "final_count": len(compressed),
            "original_tokens": current_tokens,
            "final_tokens": final_tokens,
            "dropped": len(messages) - len(compressed),
            "categories": {
                "critical": len(critical),
                "important": len(important),
                "context": len(context),
                "noise": len(noise)
            }
        }
        
        return compressed, stats
    
    async def _create_summary(self, messages: List[Dict], task: str) -> Dict:
        """Create a summary message for dropped content."""
        # Count message types
        types = defaultdict(int)
        tools_used = set()
        topics = set()
        
        for msg in messages:
            mtype = msg.get("type", "unknown")
            types[mtype] += 1
            
            content = self._extract_text(msg).lower()
            
            # Extract tool names
            if "tool_use" in str(msg):
                tool_matches = re.findall(r'"name":\s*"([^"]+)"', str(msg))
                tools_used.update(tool_matches)
            
            # Extract topics (simple keyword extraction)
            for kw in self.important_keywords + self.critical_keywords:
                if kw in content:
                    topics.add(kw)
        
        summary_text = (
            f"[Compressed {len(messages)} messages]\n"
            f"Types: {dict(types)}\n"
        )
        
        if tools_used:
            summary_text += f"Tools used: {', '.join(sorted(tools_used))}\n"
        if topics:
            summary_text += f"Topics: {', '.join(sorted(topics))}\n"
        if task:
            summary_text += f"Task context: {task}\n"
        
        return {
            "uuid": f"summary-{hashlib.md5(str(types).encode()).hexdigest()[:8]}",
            "type": "system",
            "message": {
                "role": "system",
                "content": summary_text
            },
            "timestamp": datetime.now().isoformat() + "Z",
            "parent_uuid": None,
            "session_id": "compressed",
            "version": 1,
            "compressed": True,
            "original_count": len(messages)
        }


# =============================================================================
# TASK-AWARE CONTEXT
# =============================================================================

class TaskAwareContext:
    """Context manager that tracks current task for relevance scoring."""
    
    def __init__(self, context_manager: SmartContextManager):
        self.context_manager = context_manager
        self.current_task = ""
        self.task_history = []
    
    def set_task(self, task: str):
        """Set current task for relevance scoring."""
        if self.current_task:
            self.task_history.append(self.current_task)
        self.current_task = task
    
    def get_current_task(self) -> str:
        return self.current_task
    
    async def compress_for_task(self, messages: List[Dict], target_tokens: int = None) -> Tuple[List[Dict], Dict]:
        """Compress messages with current task awareness."""
        return await self.context_manager.compress(messages, self.current_task, target_tokens)


# =============================================================================
# USAGE
# =============================================================================

async def demo():
    """Demo the smart context manager."""
    manager = SmartContextManager(max_tokens=10000, preserve_recent=10)
    
    # Sample messages
    messages = [
        {"type": "user", "message": {"role": "user", "content": "Fix the auth bug in login.py"}, "type": "user"},
        {"type": "assistant", "message": {"role": "assistant", "content": "I'll look at the login.py file"}, "type": "assistant"},
        {"type": "tool", "message": {"role": "assistant", "content": [{"type": "tool_use", "name": "Read", "input": {"path": "login.py"}}]}, "type": "tool"},
        {"type": "tool", "message": {"role": "user", "content": "File content..."}, "type": "tool"},
        {"type": "assistant", "message": {"role": "assistant", "content": "Found the bug - missing validation on line 42"}, "type": "assistant"},
        {"type": "user", "message": {"role": "user", "content": "Great, fix it"}, "type": "user"},
        {"type": "assistant", "message": {"role": "assistant", "content": "Fixed! Added validation..."}, "type": "assistant"},
        {"type": "user", "message": {"role": "user", "content": "Thanks!"}, "type": "user"},
        {"type": "assistant", "message": {"role": "assistant", "content": "You're welcome!"}, "type": "assistant"},
    ] * 5  # Repeat to exceed token limit
    
    compressed, stats = await manager.compress(messages, "fix auth bug", target_tokens=1000)
    
    print(f"Original: {stats['original_count']} messages, {stats['original_tokens']:.0f} tokens")
    print(f"Compressed: {stats['final_count']} messages, {stats['final_tokens']:.0f} tokens")
    print(f"Dropped: {stats['dropped']} messages")
    print(f"Categories: {stats['categories']}")


if __name__ == "__main__":
    asyncio.run(demo())