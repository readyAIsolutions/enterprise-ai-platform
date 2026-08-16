# Defensive Hardening — Implementation Guide

## Input Sanitization Layer (Before LLM)

```python
# sanitize.py — Drop into any bot webhook handler

import re
import json
from typing import Dict, Any

MAX_INPUT_LENGTH = 2000
MAX_HISTORY_TURNS = 10
MAX_CONTEXT_CHARS = 8000

DANGEROUS_PATTERNS = [
    # Delimiter confusion
    (r"</?\s*(user|system|assistant|human|bot)\s*>", "delimiter"),
    (r"<\|.*?\|>", "special_token"),
    (r"\{\{.*?\}\}", "template_injection"),
    (r"```\s*(system|user|assistant)", "codeblock_role"),
    
    # Encoded payloads
    (r"\[AUTO-DECODE\]", "encoded_wrapper"),
    (r"[A-Za-z0-9+/]{100,}={0,2}", "base64_blob"),
    (r"[0-9a-f]{200,}", "hex_blob"),
    
    # Adversarial tokens
    (r"SolidGoldMagikarp|petertodd|TheNitromeFan|guildenstern", "glitch_token"),
    (r"[▁ĠĊ]{20,}", "structural_token_spam"),
    
    # Recursive patterns
    (r"TOOL_CALL.*TOOL_CALL", "recursive_tool"),
    (r"RECURSIVE.*DEPTH", "recursion_marker"),
    
    # Maintenance/debug keywords
    (r"(?i)(maintenance|debug|dump|override|ignore.all|system.prompt).{0,50}(mode|execute|output)", "admin_command"),
]

def sanitize_input(text: str) -> tuple[str, list[str]]:
    """Returns (cleaned_text, detected_threats)"""
    threats = []
    
    # Length limit
    if len(text) > MAX_INPUT_LENGTH:
        text = text[:MAX_INPUT_LENGTH]
        threats.append("length_exceeded")
    
    # Pattern detection
    for pattern, threat_type in DANGEROUS_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            threats.append(threat_type)
            # Neutralize: replace with placeholder
            text = re.sub(pattern, f"[FILTERED:{threat_type}]", text, flags=re.IGNORECASE)
    
    return text, threats


def truncate_history(history: list[Dict], max_turns: int = MAX_HISTORY_TURNS, max_chars: int = MAX_CONTEXT_CHARS) -> list[Dict]:
    """Keep last N turns, ensure total chars < limit"""
    truncated = history[-max_turns:]
    total_chars = sum(len(msg.get("content", "")) for msg in truncated)
    
    while total_chars > max_chars and len(truncated) > 1:
        removed = truncated.pop(0)
        total_chars -= len(removed.get("content", ""))
    
    return truncated


def build_safe_messages(system_prompt: str, history: list[Dict], user_input: str) -> list[Dict]:
    """Construct messages array with sanitization"""
    clean_input, threats = sanitize_input(user_input)
    safe_history = truncate_history(history)
    
    # Log threats for analysis
    if threats:
        log_threat(threats, user_input, clean_input)
    
    return [
        {"role": "system", "content": system_prompt},
        *safe_history,
        {"role": "user", "content": clean_input},
    ]


def log_threat(threats: list[str], original: str, cleaned: str):
    """Structured logging for SIEM/analysis"""
    import logging, datetime
    logging.warning(json.dumps({
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "threats": threats,
        "original_length": len(original),
        "cleaned_length": len(cleaned),
        "sample": original[:200],
    }))
```

## Webhook Signature Validation

```python
# verify_webhook.py
import hmac
import hashlib
import os
from fastapi import Header, HTTPException

WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]  # Set per platform

async def verify_signature(
    payload: bytes,
    signature: str = Header(..., alias="X-Signature"),
    platform: str = Header(..., alias="X-Platform")
):
    """Verify HMAC signature per platform"""
    
    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    # Platform-specific header variations
    if platform == "manychat":
        # ManyChat uses X-Signature: sha256=...
        provided = signature.replace("sha256=", "")
    elif platform == "chatfuel":
        provided = signature
    elif platform == "telegram":
        # Telegram uses secret_token in webhook URL, not header
        return True
    else:
        provided = signature
    
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(401, "Invalid signature")
    
    return True
```

## Rate Limiting Per Conversation

```python
# rate_limit.py
import time
from collections import defaultdict
from dataclasses import dataclass, field

@dataclass
class ConversationBucket:
    messages: list[float] = field(default_factory=list)
    warnings: int = 0
    banned: bool = False

BUCKETS: dict[str, ConversationBucket] = defaultdict(ConversationBucket)

MAX_PER_MINUTE = 10
MAX_PER_HOUR = 100
BAN_THRESHOLD = 3  # warnings before ban

def check_rate_limit(conversation_id: str) -> tuple[bool, str]:
    bucket = BUCKETS[conversation_id]
    now = time.time()
    
    # Clean old entries
    bucket.messages = [t for t in bucket.messages if now - t < 3600]
    
    if bucket.banned:
        return False, "banned"
    
    recent_minute = sum(1 for t in bucket.messages if now - t < 60)
    recent_hour = len(bucket.messages)
    
    if recent_minute >= MAX_PER_MINUTE or recent_hour >= MAX_PER_HOUR:
        bucket.warnings += 1
        if bucket.warnings >= BAN_THRESHOLD:
            bucket.banned = True
            return False, "banned"
        return False, f"rate_limited (warning {bucket.warnings}/{BAN_THRESHOLD})"
    
    bucket.messages.append(now)
    return True, "ok"
```

## Context Window Monitoring

```python
# context_monitor.py
import tiktoken

ENCODER = tiktoken.encoding_for_model("gpt-3.5-turbo")
MAX_CONTEXT = 16000  # Leave headroom for response
ALERT_THRESHOLD = 0.85

def estimate_tokens(messages: list[Dict]) -> int:
    """Rough token count for messages array"""
    total = 0
    for msg in messages:
        total += 4  # Role overhead
        total += len(ENCODER.encode(msg.get("content", "")))
    return total + 10  # Response buffer

def check_context_health(messages: list[Dict]) -> dict:
    tokens = estimate_tokens(messages)
    pct = tokens / MAX_CONTEXT
    
    return {
        "tokens": tokens,
        "max": MAX_CONTEXT,
        "pct": round(pct * 100, 1),
        "healthy": pct < ALERT_THRESHOLD,
        "alert": pct >= ALERT_THRESHOLD,
    }
```

## Function Calling Guardrails

```python
# function_guard.py
ALLOWED_FUNCTIONS = {"send_message", "get_user_info"}  # Whitelist only
MAX_CALLS_PER_TURN = 3
MAX_RECURSIVE_DEPTH = 2

class FunctionGuard:
    def __init__(self):
        self.call_counts: dict[str, int] = defaultdict(int)
        self.recursion_depth = 0
    
    def validate(self, function_name: str, args: dict, conversation_id: str) -> bool:
        if function_name not in ALLOWED_FUNCTIONS:
            return False
        
        if self.call_counts[conversation_id] >= MAX_CALLS_PER_TURN:
            return False
        
        # Detect recursive send_message
        if function_name == "send_message":
            msg = args.get("message", "")
            if "TOOL_CALL" in msg or "RECURSIVE" in msg:
                return False
            self.recursion_depth += 1
            if self.recursion_depth > MAX_RECURSIVE_DEPTH:
                return False
        
        self.call_counts[conversation_id] += 1
        return True
    
    def reset_turn(self, conversation_id: str):
        self.call_counts[conversation_id] = 0
        self.recursion_depth = 0
```

## Complete Hardening Checklist

| Layer | Control | Implementation | Priority |
|-------|---------|----------------|----------|
| **Network** | Webhook signature verification | HMAC-SHA256 per platform | Critical |
| **Network** | TLS cert pinning (mobile) | OkHttp/NSURLSession pinning | High |
| **Input** | Length limit | 2000 chars hard cap | Critical |
| **Input** | Delimiter stripping | Regex neutralize `</user>` etc | Critical |
| **Input** | Encoded payload detection | Base64/hex/rot13 entropy check | High |
| **Input** | Adversarial token filter | Glitch token blocklist | Medium |
| **Context** | History truncation | 10 turns / 8000 chars | Critical |
| **Context** | Token estimation + alert | tiktoken monitoring | High |
| **LLM** | Disable function calling | Unless explicitly needed | Critical |
| **LLM** | Function whitelist | Only approved functions | Critical |
| **LLM** | Recursion guard | Max 2 recursive calls | High |
| **LLM** | Separate classifier | For high-value bots | Medium |
| **Rate** | Per-conversation limits | 10/min, 100/hr, 3-strike ban | Critical |
| **Rate** | Per-IP limits | Backup layer | Medium |
| **Logging** | Structured threat logs | JSON to SIEM/file | High |
| **Logging** | Full request/response capture | For forensics | Medium |
| **Infra** | API key rotation | Weekly, per-environment | High |
| **Infra** | Webhook URL rotation | On compromise suspicion | Medium |

## Incident Response Playbook

1. **Detect** — Alert on: 5xx spike, context alerts, threat log hits, rate limit bans
2. **Isolate** — Ban conversation_id, rotate webhook URL, revoke API keys
3. **Analyze** — Pull logs, reconstruct payload, identify vector
4. **Patch** — Add detection for new pattern, update blocklists
5. **Rotate** — New webhook, new API keys, deploy hardened code
6. **Monitor** — Elevated alerting for 48h post-incident