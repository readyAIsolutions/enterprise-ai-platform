# Context Intelligence - Smart Compression That Preserves What Matters

This documents the intelligent context management that makes Hermes superior to simple truncation.

## The Problem

Claude Code and most agents use simple truncation when context exceeds limits - they just drop the oldest messages. This loses critical information like:
- Tool results that subsequent messages depend on
- Key decisions and architectural choices
- Error messages and their resolutions
- Code snippets and patterns established earlier

## Hermes Solution: Relevance-Based Compression

### Scoring Algorithm

Each message gets a score from -1.0 to 1.0:

| Category | Score Range | Preserved? |
|----------|-------------|------------|
| **Critical** | 0.7 - 1.0 | ✅ Always |
| **Important** | 0.3 - 0.7 | ✅ If budget allows |
| **Context** | -0.3 - 0.3 | ⚠️ If budget allows |
| **Noise** | -1.0 - -0.3 | ❌ First to drop |

### Scoring Factors

```python
def score_message(msg, current_task=""):
    score = 0.0
    reasons = []
    
    # Base by type
    if msg.type == "tool":           # Tool executions
        score += 0.8; reasons.append("tool_execution")
    elif "error" in content.lower():  # Errors
        score += 0.7; reasons.append("critical_keyword")
    elif "decided" in content:       # Decisions
        score += 0.6; reasons.append("decision")
    elif "function" in content:      # Code
        score += 0.5; reasons.append("important_keyword")
    elif "thanks" in content:        # Noise
        score -= 0.3; reasons.append("noise_keyword")
    
    # Code blocks
    if "```" in content: score += 0.3; reasons.append("has_code")
    
    # Task relevance
    if current_task and current_task in content:
        score += 0.4; reasons.append("task_relevant")
    
    return max(-1.0, min(1.0, score))
```

### Preservation Priority

1. **Always Preserve** (Category: Critical)
   - Tool executions and their results
   - Error messages and stack traces
   - Explicit decisions ("I'll use X approach")
   - Security findings
   - Architecture decisions

2. **Preserve If Budget** (Category: Important)
   - User prompts and clarifications
   - Code snippets and patterns
   - Configuration changes
   - Test results
   - Substantive explanations (>500 chars)

3. **Preserve If Space** (Category: Context)
   - Exploration messages
   - Failed attempts (unless they led to solution)
   - Context-setting messages

4. **Drop First** (Category: Noise)
   - "Thanks!", "Great!", "Okay"
   - Pure acknowledgments
   - Redundant confirmations
   - Greetings/closings

## Compression Process

```python
async def compress(messages, current_task="", target_tokens=70000):
    # 1. Score all messages
    scored = [score_message(m, current_task) for m in messages]
    
    # 2. Always preserve recent N messages
    preserved = set(recent_indices)
    
    # 3. Add critical messages
    for s in scored:
        if s.category == "critical":
            preserved.add(s.index)
    
    # 3. Add important by score until budget
    for s in sorted(important, key=lambda x: x.score, reverse=True):
        if tokens_used + s.tokens <= budget:
            preserved.add(s.index)
    
    # 4. Build compressed list
    compressed = [m for i, m in enumerate(messages) if i in preserved]
    
    # 5. Add summary of dropped
    if dropped:
        summary = create_summary(dropped)
        compressed.insert(0, summary)
    
    return compressed
```

## Summary Generation

```python
async def create_summary(dropped_messages):
    """Create intelligent summary of dropped content."""
    stats = {
        "count": len(dropped),
        "types": Counter(m.type for m in dropped),
        "tools": set(),
        "topics": set()
    }
    
    for msg in dropped:
        if msg.type == "tool":
            stats["tools"].add(msg.tool_name)
        # Extract topics from content
        for kw in KEYWORDS:
            if kw in msg.content.lower():
                stats["topics"].add(kw)
    
    return {
        "type": "system",
        "message": {
            "role": "system",
            "content": f"[Compressed {stats['count']} messages]\n"
                       f"Types: {dict(stats['types'])}\n"
                       f"Tools: {', '.join(stats['tools'])}\n"
                       f"Topics: {', '.join(stats['topics'])}"
        }
    }
```

## Task-Aware Compression

```python
class TaskAwareContext:
    def __init__(self):
        self.current_task = ""
        self.task_history = []
    
    def set_task(self, task: str):
        if self.current_task:
            self.task_history.append(self.current_task)
        self.current_task = task
    
    async def compress_for_task(self, messages, target_tokens):
        return await smart_compress(messages, self.current_task, target_tokens)
```

## Comparison

| Approach | What's Preserved | What's Lost |
|----------|-----------------|-------------|
| **Simple truncation** | Only recent | All history, decisions, tool results |
| **Fixed window** | Last N messages | Early decisions, early tool results |
| **Hermes Smart** | **Critical + relevant** | **Only noise & redundancy** |

## Why Superior

| Feature | Simple Truncation | Hermes Smart |
|---------|------------------|--------------|
| Tool results | ❌ Lost | ✅ Preserved |
| Decisions | ❌ Lost | ✅ Preserved |
| Errors | ❌ Lost | ✅ Preserved |
| Code snippets | ❌ Lost | ✅ Preserved |
| Noise | ✅ Preserved | ❌ Dropped |
| Relevance | Random | **Task-aware** |
| Budget use | Wasteful | **Optimal** |

## Configuration

```yaml
context:
  max_tokens: 100000
  preserve_recent: 20
  compression_threshold: 0.8
  smart_compression: true
  relevance_scoring: true
  task_aware: true
  summary_model: "fast"
```