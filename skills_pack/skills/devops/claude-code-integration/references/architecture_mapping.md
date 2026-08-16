# Architecture Mapping: Claude Code → Hermes

## Overview
This document maps every major component from Claude Code's TypeScript/React (Ink) codebase to its Hermes Python equivalent.

## Component-by-Component Mapping

### 1. Application Root

| Claude Code | Hermes | Description |
|-------------|--------|-------------|
| `src/ink/components/App.tsx` | `hermes_cli/tui/app.py` | Main TUI application class |
| `src/main.ts` | `hermes_cli/main.py` | CLI entry point |
| `src/cli.ts` | `hermes_cli/cli.py` | Chat/repl loop |

**Key patterns mapped:**
- Ink `PureComponent` → Python class with render method
- React context providers → Python context managers
- `componentDidMount`/`componentWillUnmount` → `__aenter__`/`__aexit__`
- Raw mode handling → `termios`/`tty` module
- Key parsing state machine → `KeyParser` class
- Mouse tracking (SGR 1006) → `MouseTracker` class

### 2. Shell Command Execution

| Claude Code | Hermes | Description |
|-------------|--------|-------------|
| `src/utils/ShellCommand.ts` | `hermes_cli/local_agent.py` | `ShellCommand` class |
| `src/utils/wrapSpawn.ts` | `hermes_cli/local_agent.py` | `wrap_spawn()` function |

**Key patterns mapped:**
- `ChildProcess` → `asyncio.subprocess.Process`
- `tree-kill` → `os.killpg`/`process.kill()`
- `StreamWrapper` → `asyncio.StreamReader` + callbacks
- `TaskOutput` (file-backed) → `TaskOutput` class with file fd
- Backgrounding on timeout → `auto_background` parameter
- Size watchdog → `asyncio.create_task` polling file size
- Output truncation → `max_output_bytes` limit

### 3. Background Task System

| Claude Code | Hermes | Description |
|-------------|--------|-------------|
| `src/tasks/LocalMainSessionTask.ts` | `hermes_cli/tasks/background.py` | `BackgroundTaskManager` |
| `src/tasks/LocalAgentTask.ts` | `hermes_cli/tasks/agent_task.py` | `AgentTask` class |

**Key patterns mapped:**
- `registerMainSessionTask` → `start_background_session()`
- `completeMainSessionTask` → `complete_background_session()`
- `startBackgroundSession` → `delegate_to_subagent()`
- Isolated transcripts → `TaskOutput` with symlink
- `runWithAgentContext` → `AgentContext` async context manager
- Progress tracking → `TaskOutput` progress callbacks

### 4. Hooks System

| Claude Code | Hermes | Description |
|-------------|--------|-------------|
| `src/utils/hooks.ts` | `hermes_cli/hooks.py` | `HooksManager` class |
| `src/hooks/` | `hermes_cli/hooks/` | Hook type definitions |

**Key patterns mapped:**
- Sync hooks (blocking) → `execute_sync_hook()` with timeout
- Async hooks (fire-and-forget) → `execute_async_hook()` background
- Hook matching → `HookMatcher` with glob patterns
- Plugin hooks → `PluginHookMatcher` integration
- Permission hooks → `PermissionRequestHook` special handling
- Environment injection → `subprocessEnv` + hook-specific vars

### 5. Memory/CLAUDE.md System

| Claude Code | Hermes | Description |
|-------------|--------|-------------|
| `src/utils/claudemd.ts` | `hermes_cli/memory.py` | `MemoryLoader` class |
| `src/memdir/` | `hermes_cli/memdir/` | Path resolution |

**Key patterns mapped:**
- 4-tier loading (managed → user → project → local) → `load_memory_files()`
- `@include` directive → `parse_include_directives()`
- Frontmatter `paths` globs → `FrontmatterParser` with picomatch
- HTML comment stripping → `strip_html_comments()` (marked lexer)
- AutoMem entrypoints → `getAutoMemEntrypoint()`
- Truncation → `truncateEntrypointContent()`
- Content diff tracking → `contentDiffersFromDisk` flag

### 6. Agent/Subagent Delegation

| Claude Code | Hermes | Description |
|-------------|--------|-------------|
| `src/tools/AgentTool/` | `hermes_cli/agent_tool.py` | `AgentTool` class |
| `src/utils/agentContext.ts` | `hermes_cli/agent_context.py` | `AgentContext` manager |

**Key patterns mapped:**
- `AgentDefinition` → `AgentDefinition` Pydantic model
- `SubagentContext` → `AgentContext` with `agent_id`, `agent_type`
- `AsyncLocalStorage` → Python `contextvars.ContextVar`
- Skill scoping → `invoked_skills` per agent_id
- Transcript isolation → Sidechain transcript per agent

### 7. Tool System

| Claude Code | Hermes | Description |
|-------------|--------|-------------|
| `src/Tool.js` | `hermes_cli/tools/__init__.py` | `Tool` base class |
| `src/tools/` | `hermes_cli/tools/` | Individual tool implementations |

**Key patterns mapped:**
- `ToolUseContext` → `ToolContext` with session, config, permissions
- Permission rules → `permission_rule_value_from_string()`
- Approval flow → `ask_permission()` with allow/deny/modify
- Tool result formatting → `ToolResultMessage` with structured output
- Background tools → `background` flag in tool definition

### 8. Agent Loop (query.js)

| Claude Code | Hermes | Description |
|-------------|--------|-------------|
| `src/query.js` | `hermes_cli/agent_loop.py` | `agent_loop()` function |
| `src/utils/agentLoop.ts` | `hermes_cli/agent_loop.py` | Loop utilities |

**Key patterns mapped:**
- `for await (const event of query(...))` → `async for event in agent_loop()`
- Message types (user/assistant/system/tool) → Pydantic discriminated union
- Token counting → `roughTokenCountEstimation()`
- Tool activity tracking → `recentActivities` in progress
- Max turns → `max_turns` parameter
- Abort handling → `AbortSignal` / `asyncio.CancelledError`

### 9. Settings/Configuration

| Claude Code | Hermes | Description |
|-------------|--------|-------------|
| `src/utils/settings/settings.ts` | `hermes_cli/config.py` | `ConfigManager` |
| `src/utils/settings/types.ts` | `hermes_cli/config.py` | Pydantic models |

**Key patterns mapped:**
- Hierarchical sources (default → user → project → env) → `ConfigManager.load()`
- Source tracking → `ConfigSource` enum
- Validation → Pydantic validators
- Migration → `migrate_config()`
- Secrets → `.env` + external secret managers

### 10. Keybindings/Input

| Claude Code | Hermes | Description |
|-------------|--------|-------------|
| `src/keybindings/defaultBindings.ts` | `hermes_cli/keybindings.py` | `KeybindingManager` |
| `src/parse-keypress.ts` | `hermes_cli/key_parser.py` | `KeyParser` |

**Key patterns mapped:**
- CSI u / Kitty protocol → `KeyParser` with both formats
- Key sequences → `ParsedKey` with sequence, modifiers
- Multi-click detection → `MultiClickTracker`
- Focus events (DECSET 1004) → `FocusTracker`
- Bracketed paste → `BracketedPasteHandler`

### 11. Session Management

| Claude Code | Hermes | Description |
|-------------|--------|-------------|
| `src/utils/sessionStorage.ts` | `hermes_cli/session.py` | `SessionManager` |
| `src/utils/transcript.ts` | `hermes_cli/transcript.py` | `TranscriptWriter` |

**Key patterns mapped:**
- JSONL transcript format → `TranscriptWriter` append-only
- Sidechain transcripts → `TaskOutput` symlink pattern
- `/clear` handling → Re-link symlink, preserve background tasks
- Compression → `compress_session()` with summarization
- Resumption → `load_session()` with message reconstruction

### 12. Permissions

| Claude Code | Hermes | Description |
|-------------|--------|-------------|
| `src/utils/permissions/` | `hermes_cli/permissions.py` | `PermissionManager` |

**Key patterns mapped:**
- Allow/ask/deny rules → `PermissionRule` with glob patterns
- Command allowlist → `command_allowlist` config
- Hook-based approval → `PermissionRequestHook`
- Tool-specific rules → `tool.<name>` permission keys

## Implementation Status

| Component | Status | Location |
|-----------|--------|----------|
| TUI App | ✅ Complete | `hermes_cli/tui/app.py` |
| Shell Command | ✅ Complete | `hermes_cli/local_agent.py` |
| Background Tasks | ✅ Complete | `hermes_cli/tasks/background.py` |
| Hooks System | ✅ Complete | `hermes_cli/hooks.py` |
| Memory System | ✅ Complete | `hermes_cli/memory.py` |
| Agent Delegation | ✅ Complete | `hermes_cli/agent_tool.py` |
| Tool System | ✅ Complete | `hermes_cli/tools/__init__.py` |
| Agent Loop | ✅ Complete | `hermes_cli/agent_loop.py` |
| Config | ✅ Complete | `hermes_cli/config.py` |
| Keybindings | ✅ Complete | `hermes_cli/keybindings.py` |
| Session Mgmt | ✅ Complete | `hermes_cli/session.py` |
| Permissions | ✅ Complete | `hermes_cli/permissions.py` |

## Running the Integration

```bash
# All components available via:
hermes --tui                    # TUI mode (App.tsx equivalent)
hermes local-agent             # Local agent server (ShellCommand equivalent)
hermes chat -z "prompt"        # One-shot (oneshot mode)
hermes hooks add PreToolUse... # Hooks system
hermes memory show             # Memory system
```