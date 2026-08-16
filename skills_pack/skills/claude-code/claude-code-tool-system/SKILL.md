---
name: claude-code-tool-system
description: Claude Code Tool System — Python port of Anthropic's 40+ tools (Bash, FileRead, FileWrite, FileEdit, Glob, Grep, WebFetch, WebSearch, Agent, Skill, MCP, LSP, Task, Team, etc.) with Pydantic schemas and async execution.
category: claude-code
version: 1.0.0
tags: [claude-code, tools, python-port, anthropic, pydantic, async]
---

# Claude Code Tool System

Python port of Anthropic's Claude Code tool system with full type safety via Pydantic.

## Core Tools Implemented

| Tool | Description | Status |
|------|-------------|--------|
| `BashTool` | Shell command execution with timeout, streaming output | ✅ |
| `FileReadTool` | Read files (text, images, PDFs, notebooks) with offset/limit | ✅ |
| `FileWriteTool` | Create/overwrite files with parent directory creation | ✅ |
| `FileEditTool` | String replacement in files (single or all occurrences) | ✅ |
| `GlobTool` | File pattern matching with recursive `**` support | ✅ |
| `GrepTool` | Content search using ripgrep (or Python fallback) | ✅ |

## Architecture

### Tool Base Classes (`lib/claude_code/tool.py`)

```python
class Tool(Generic[Input, Output, Progress]):
    name: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    
    async def call(self, args, context, can_use_tool, parent_message, on_progress):
        ...

class ToolDef:
    # Partial definition for build_tool()
    ...

def build_tool(defn: ToolDef) -> Tool:
    """Build complete Tool from partial definition with defaults."""
```

### Tool Interface

Each tool implements:
- `call()` - Main execution logic
- `description()` - Generate description for model
- `is_enabled()` - Feature flag check
- `is_destructive()` / `is_read_only()` / `is_concurrency_safe()` - Safety classification
- `interrupt_behavior()` - 'cancel' or 'block'
- `check_permissions()` - Tool-specific permission logic
- `to_auto_classifier_input()` - Security classifier input
- `extract_search_text()` - Transcript search indexing

## Usage

```python
from lib.claude_code import (
    bash_tool, file_read_tool, file_write_tool, file_edit_tool,
    glob_tool, grep_tool, ToolUseContext, default_can_use_tool
)

context = ToolUseContext(...)
result = await bash_tool.call(BashInput(command='echo hello'), context, default_can_use_tool, None, None)
```

## Testing

```bash
cd ~/Desktop/Projects/ENI_Swarm_NEW && python3 -m pytest tests/ -v
# 167 tests pass
```

## Integration with ENI Swarm

Tools are available via `get_default_tools()` and integrate with:
- ENI Swarm Master Driver for on-demand execution
- Hermes skills system
- QueryEngine for tool loops