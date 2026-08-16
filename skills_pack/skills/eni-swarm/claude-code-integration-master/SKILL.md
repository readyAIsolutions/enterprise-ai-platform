---
name: claude-code-integration-master
description: Master integration skill for porting Claude Code (Anthropic's official CLI) into Hermes + ENI Swarm. Covers tool system, command system, query engine, services, bridge, coordinator, skills, plugins, permissions, state management.
category: eni-swarm
version: 1.0.0
tags: [claude-code, integration, hermes, eni-swarm, anthropic, typescript, python-port]
---

# Claude Code → Hermes/ENI Swarm Integration Master Plan

## Source Analysis Complete

**Source**: `~/Downloads/claude-code-source-code-backup/src/` (Leaked 2026-03-31, ~512K lines TypeScript)
**Runtime**: Bun + React/Ink (terminal UI)
**Architecture**: Commander.js CLI + Tool/Command/QueryEngine + Services

---

## Core Systems to Port

### 1. Tool System (`src/tools.ts`, `src/Tool.ts`, `src/tools/`) — 40+ Tools
| Tool | Purpose | Port Priority |
|------|---------|---------------|
| `BashTool` | Shell command execution | CRITICAL |
| `FileReadTool` | File reading (images, PDFs, notebooks) | CRITICAL |
| `FileWriteTool` | File creation/overwrite | CRITICAL |
| `FileEditTool` | Partial file modification (string replacement) | CRITICAL |
| `GlobTool` | File pattern matching search | CRITICAL |
| `GrepTool` | ripgrep-based content search | CRITICAL |
| `WebFetchTool` | Fetch URL content | HIGH |
| `WebSearchTool` | Web search | HIGH |
| `AgentTool` | Sub-agent spawning | CRITICAL (ENI Swarm native) |
| `SkillTool` | Skill execution | CRITICAL (Hermes skills) |
| `MCPTool` | MCP server tool invocation | HIGH |
| `LSPTool` | Language Server Protocol integration | HIGH |
| `NotebookEditTool` | Jupyter notebook editing | MEDIUM |
| `TaskCreateTool`/`TaskUpdateTool`/`TaskListTool`/`TaskGetTool` | Task management | HIGH |
| `SendMessageTool` | Inter-agent messaging | HIGH (ENI FIFO) |
| `TeamCreateTool`/`TeamDeleteTool` | Team agent management | HIGH |
| `EnterPlanModeTool`/`ExitPlanModeV2Tool` | Plan mode toggle | MEDIUM |
| `EnterWorktreeTool`/`ExitWorktreeTool` | Git worktree isolation | MEDIUM |
| `ToolSearchTool` | Deferred tool discovery | HIGH |
| `CronCreateTool`/`CronDeleteTool`/`CronListTool` | Scheduled triggers | MEDIUM |
| `RemoteTriggerTool` | Remote trigger | MEDIUM |
| `SleepTool` | Proactive mode wait | MEDIUM |
| `SyntheticOutputTool` | Structured output generation | HIGH |
| `AskUserQuestionTool` | Ask user questions | MEDIUM |
| `ConfigTool` | Config management | MEDIUM |
| `VerifyPlanExecutionTool` | Plan verification | MEDIUM |
| `ListMcpResourcesTool`/`ReadMcpResourceTool` | MCP resources | MEDIUM |
| `BriefTool` | Brief output | LOW |
| `TungstenTool` | Internal tool | LOW |
| `REPLTool` | REPL wrapper | LOW |
| `PowerShellTool` | PowerShell execution | LOW |

### 2. Command System (`src/commands.ts`, `src/commands/`) — 50+ Slash Commands
| Command | Purpose | Port Priority |
|---------|---------|---------------|
| `/commit` | Git commit | HIGH |
| `/review` | Code review | HIGH |
| `/compact` | Context compression | CRITICAL |
| `/mcp` | MCP server management | HIGH |
| `/config` | Settings management | HIGH |
| `/doctor` | Environment diagnostics | HIGH |
| `/login`/`/logout` | Authentication | HIGH |
| `/memory` | Persistent memory management | CRITICAL |
| `/skills` | Skill management | CRITICAL |
| `/tasks` | Task management | HIGH |
| `/vim` | Vim mode toggle | MEDIUM |
| `/diff` | View changes | HIGH |
| `/cost` | Usage cost | HIGH |
| `/theme` | Change theme | MEDIUM |
| `/context` | Context visualization | HIGH |
| `/pr_comments` | PR comments | MEDIUM |
| `/resume` | Restore session | HIGH |
| `/share` | Share session | MEDIUM |
| `/desktop`/`/mobile` | App handoff | MEDIUM |
| `/init` | Project initialization | HIGH |
| `/agents` | Agent management | HIGH |
| `/branch` | Git branch | MEDIUM |
| `/env` | Environment variables | MEDIUM |
| `/export` | Export conversation | MEDIUM |
| `/model` | Model selection | HIGH |
| `/tag` | Tagging | LOW |
| `/output-style` | Output styling | MEDIUM |
| `/hooks` | Hook management | HIGH |
| `/files` | Tracked files | MEDIUM |
| `/status` | Status display | HIGH |
| `/plan` | Plan mode | HIGH |
| `/fast` | Fast mode | MEDIUM |
| `/passes` | Passes | LOW |
| `/permissions` | Permission management | HIGH |
| `/upgrade` | Upgrade | MEDIUM |
| `/security-review` | Security review | HIGH |
| `/terminal-setup` | Terminal setup | MEDIUM |
| `/rewind` | Rewind | MEDIUM |
| `/summary` | Summarize | MEDIUM |
| `/ultraplan` | Ultra planning | HIGH |
| `/thinkback`/`/thinkback-play` | Thinkback | MEDIUM |
| `/teleport` | Teleport | MEDIUM |
| `/chrome` | Chrome integration | LOW |
| `/issue` | GitHub issues | MEDIUM |
| `/btw` | Quick note | LOW |
| `/add-dir` | Add directory | LOW |
| `/autofix-pr` | Auto-fix PR | MEDIUM |
| `/backfill-sessions` | Backfill sessions | LOW |
| `/bughunter` | Bug hunter | MEDIUM |
| `/ctx_viz` | Context visualization | MEDIUM |
| `/break-cache` | Break cache | LOW |
| `/clear` | Clear screen | LOW |
| `/copy` | Copy last message | LOW |
| `/debug-tool-call` | Debug tool call | MEDIUM |
| `/effort` | Effort level | MEDIUM |
| `/extra-usage` | Extra usage | LOW |
| `/feedback` | Feedback | LOW |
| `/good-claude` | Good claude | LOW |
| `/heapdump` | Heap dump | LOW |
| `/help` | Help | HIGH |
| `/ide` | IDE integration | HIGH |
| `/install-github-app` | Install GitHub app | LOW |
| `/install-slack-app` | Install Slack app | LOW |
| `/keybindings` | Keybindings | MEDIUM |
| `/mock-limits` | Mock limits | LOW |
| `/oauth-refresh` | OAuth refresh | LOW |
| `/privacy-settings` | Privacy settings | MEDIUM |
| `/rate-limit-options` | Rate limit options | MEDIUM |
| `/release-notes` | Release notes | LOW |
| `/remote-env` | Remote env | LOW |
| `/remote-setup` | Remote setup | MEDIUM |
| `/rename` | Rename | LOW |
| `/reset-limits` | Reset limits | LOW |
| `/sandbox-toggle` | Sandbox toggle | HIGH |
| `/stickers` | Stickers | LOW |
| `/subscribe-pr` | Subscribe PR | LOW |
| `/tag` | Tag | LOW |
| `/theme` | Theme | MEDIUM |
| `/torch` | Torch | LOW |
| `/upgrade` | Upgrade | MEDIUM |
| `/usage` | Usage | HIGH |
| `/version` | Version | LOW |
| `/vim` | Vim mode | MEDIUM |
| `/voice` | Voice input | LOW |
| `/workflows` | Workflows | MEDIUM |

### 3. QueryEngine (`src/QueryEngine.ts`, `src/query.ts`) — Core LLM Orchestration
- Streaming API calls with tool loops
- Cost tracking, token counting
- Permission handling, thinking mode
- Message normalization, transcript recording
- Budget limits, max turns, structured output
- Orphaned permission handling
- Snip compaction integration

### 4. Service Layer (`src/services/`)
| Service | Purpose | Port Priority |
|---------|---------|---------------|
| `api/` | Anthropic API client, file API, bootstrap | CRITICAL |
| `mcp/` | MCP server connection/management | CRITICAL |
| `oauth/` | OAuth 2.0 auth flow | HIGH |
| `lsp/` | LSP manager | HIGH |
| `analytics/` | GrowthBook feature flags/analytics | MEDIUM |
| `plugins/` | Plugin loader | HIGH |
| `compact/` | Conversation context compression | CRITICAL |
| `policyLimits/` | Org policy limits | MEDIUM |
| `remoteManagedSettings/` | Remote managed settings | MEDIUM |
| `extractMemories/` | Auto memory extraction | HIGH |
| `tokenEstimation.ts` | Token count estimation | HIGH |
| `teamMemorySync/` | Team memory sync | HIGH |

### 5. Bridge System (`src/bridge/`) — IDE Integration
- `bridgeMain.ts` — Bridge main loop
- `bridgeMessaging.ts` — Message protocol
- `bridgePermissionCallbacks.ts` — Permission callbacks
- `replBridge.ts` — REPL session bridge
- `jwtUtils.ts` — JWT auth
- `sessionRunner.ts` — Session execution management

### 6. Coordinator (`src/coordinator/`) — Multi-Agent Orchestration
- Sub-agent spawning via `AgentTool`
- `TeamCreateTool` for team-level parallel work
- Multi-agent coordination

### 7. Skills System (`src/skills/`) — Reusable Workflows
- Skill definition, loading, execution via `SkillTool`
- Dynamic skill discovery
- Bundled skills

### 8. Plugin Architecture (`src/plugins/`)
- Built-in and third-party plugin loading
- Plugin commands/skills integration

### 9. Permission System (`src/hooks/toolPermission/`)
- Checks permissions on every tool invocation
- Prompts user for approval/denial
- Auto-resolves based on permission mode (`default`, `plan`, `bypassPermissions`, `auto`)

### 10. State Management (`src/state/`, `src/bootstrap/state.ts`)
- `AppState` — Global app state
- `bootstrap/state.ts` — Session-scoped state
- Redux-like store with middleware

### 11. Context Collection (`src/context.ts`)
- `getSystemContext()` — Git status, cache breaker
- `getUserContext()` — CLAUDE.md files, current date

### 12. Memory System (`src/memdir/`)
- Persistent memory directory
- Automatic memory extraction

---

## Port Strategy

### Phase 1: Core Infrastructure (Week 1)
1. **Tool Base Classes** → Python `Tool`, `ToolDef`, `build_tool` with Zod→Pydantic
2. **Command Base Classes** → Python `Command`, `PromptCommand`, `LocalCommand`
3. **QueryEngine** → Python async generator-based query loop
4. **Permission System** → Python permission context + checkers
5. **State Management** → Python store with middleware

### Phase 2: Essential Tools (Week 1-2)
1. `BashTool`, `FileReadTool`, `FileWriteTool`, `FileEditTool` (CRITICAL)
2. `GlobTool`, `GrepTool` (ripgrep integration)
3. `WebFetchTool`, `WebSearchTool`
4. `AgentTool` (integrate with ENI Swarm master driver)
5. `SkillTool` (integrate with Hermes skills)
6. `MCPTool`, `LSPTool`

### Phase 3: Advanced Tools (Week 2)
1. Task management tools
2. Team/agent management tools
3. MCP resource tools
4. Plan mode tools
5. Worktree tools
6. Cron tools

### Phase 4: Command System (Week 2-3)
1. Core commands: `/commit`, `/review`, `/compact`, `/mcp`, `/config`, `/doctor`, `/login`, `/logout`
2. Memory/skills: `/memory`, `/skills`, `/tasks`
3. Git/editing: `/diff`, `/context`, `/pr_comments`, `/resume`, `/init`, `/branch`, `/files`, `/diff`
4. System: `/status`, `/cost`, `/theme`, `/vim`, `/plan`, `/fast`, `/permissions`, `/upgrade`, `/security-review`

### Phase 5: Services (Week 3)
1. API client (Anthropic + OpenRouter + free-router)
2. MCP client/server
3. LSP manager
4. Compact service (context compression)
5. Plugin loader
6. Memory extraction

### Phase 6: Integration (Week 3-4)
1. ENI Swarm master driver ↔ QueryEngine
2. Hermes skills ↔ SkillTool
3. ENI FIFO ↔ SendMessageTool
4. Dashboard ↔ QueryEngine status
5. Free Model Router ↔ Model selection

### Phase 7: Bridge & Coordinator (Week 4)
1. IDE bridge (VS Code, JetBrains)
2. Multi-agent coordinator
3. Team management

---

## Integration Points with Existing ENI Swarm

| ENI Swarm Component | Claude Code Component | Integration |
|---------------------|----------------------|-------------|
| `eni-swarm-master-driver` | `QueryEngine` + `AgentTool` | Replace `hermes run` with `QueryEngine.submitMessage()` |
| `eni-swarm-orchestrator` | `Coordinator` + `TeamCreateTool` | Native multi-agent coordination |
| `eni-swarm-worker-pool` | `WorkerPool` | Already similar architecture |
| `eni-swarm-compression` | `CompactService` | Use PAQ8/Wenyan/PXPipe for context compression |
| Hermes Skills | `SkillTool` + `skills/` | Direct mapping |
| Free Model Router | Model selection in `QueryEngine` | Auto-fallback integration |
| ENI FIFO | `SendMessageTool` | Direct mapping |
| Dashboard | `QueryEngine` status events | Real-time metrics |

---

## File Structure for Port

```
~/Desktop/Projects/ENI_Swarm_NEW/
├── lib/
│   ├── claude_code/
│   │   ├── __init__.py
│   │   ├── tool.py              # Tool base classes (Pydantic + build_tool)
│   │   ├── command.py           # Command base classes
│   │   ├── query_engine.py      # QueryEngine port
│   │   ├── permission.py        # Permission system
│   │   ├── state.py             # State management
│   │   ├── context.py           # Context collection
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── bash.py
│   │   │   ├── file_read.py
│   │   │   ├── file_write.py
│   │   │   ├── file_edit.py
│   │   │   ├── glob_tool.py
│   │   │   ├── grep_tool.py
│   │   │   ├── web_fetch.py
│   │   │   ├── web_search.py
│   │   │   ├── agent.py
│   │   │   ├── skill.py
│   │   │   ├── mcp_tool.py
│   │   │   ├── lsp_tool.py
│   │   │   ├── task.py
│   │   │   ├── send_message.py
│   │   │   ├── team.py
│   │   │   ├── notebook_edit.py
│   │   │   ├── cron.py
│   │   │   ├── plan_mode.py
│   │   │   ├── worktree.py
│   │   │   ├── tool_search.py
│   │   │   ├── config.py
│   │   │   ├── verify_plan.py
│   │   │   ├── mcp_resources.py
│   │   │   ├── brief.py
│   │   │   ├── ask_user.py
│   │   │   ├── sleep.py
│   │   │   ├── remote_trigger.py
│   │   │   ├── synthetic_output.py
│   │   │   └── ...
│   │   ├── commands/
│   │   │   ├── __init__.py
│   │   │   ├── commit.py
│   │   │   ├── review.py
│   │   │   ├── compact.py
│   │   │   ├── mcp.py
│   │   │   ├── config.py
│   │   │   ├── doctor.py
│   │   │   ├── auth.py
│   │   │   ├── memory.py
│   │   │   ├── skills.py
│   │   │   ├── tasks.py
│   │   │   ├── diff.py
│   │   │   ├── cost.py
│   │   │   ├── context.py
│   │   │   ├── pr_comments.py
│   │   │   ├── resume.py
│   │   │   ├── init.py
│   │   │   ├── agents.py
│   │   │   ├── branch.py
│   │   │   ├── env.py
│   │   │   ├── export.py
│   │   │   ├── model.py
│   │   │   ├── status.py
│   │   │   ├── plan.py
│   │   │   ├── fast.py
│   │   │   ├── permissions.py
│   │   │   ├── security_review.py
│   │   │   └── ...
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── api.py
│   │   │   ├── mcp.py
│   │   │   ├── lsp.py
│   │   │   ├── compact.py
│   │   │   ├── plugins.py
│   │   │   ├── memory_extract.py
│   │   │   └── team_memory.py
│   │   ├── bridge/
│   │   │   ├── __init__.py
│   │   │   ├── main.py
│   │   │   ├── messaging.py
│   │   │   └── session_runner.py
│   │   ├── coordinator/
│   │   │   ├── __init__.py
│   │   │   └── coordinator.py
│   │   └── skills/
│   │       ├── __init__.py
│   │       ├── loader.py
│   │       └── bundled/
│   ├── eni/                     # Existing ENI modules
│   └── swarm/                   # Existing Swarm modules
```

---

## Testing Strategy

### Unit Tests (per component)
- Tool input validation, execution, rendering
- Command parsing, execution
- QueryEngine message flow, tool loops, cost tracking
- Permission checks
- State mutations

### Integration Tests
- Full query cycle with multiple tools
- Multi-agent coordination
- MCP server connection
- LSP integration
- Plugin loading
- Bridge communication

### ENI Swarm Integration Tests
- Master driver + QueryEngine
- Orchestrator + Coordinator
- Skills system end-to-end
- Dashboard real-time updates
- Free router model fallback

### Hard Bug Testing (User Requirement)
```bash
# Run all tests
cd ~/Desktop/Projects/ENI_Swarm_NEW && python -m pytest tests/ -v --tb=short

# Stress test swarm
eni-swarm start --project TEST --workers 10
eni-swarm task add --name stress_test --task "Run 100 parallel file operations"
eni-swarm status

# Test all tools
for tool in bash file_read file_write file_edit glob grep web_fetch web_search; do
  eni-swarm task add --name test_$tool --task "Test $tool with various inputs"
done

# Test commands
for cmd in commit review compact mcp config doctor memory skills tasks diff cost context; do
  eni-swarm task add --name test_$cmd --task "Execute /$cmd with test project"
done
```

---

## Skills to Create

1. `claude-code-tool-system` - Tool base classes + all 40+ tools
2. `claude-code-command-system` - Command base classes + all 50+ commands
3. `claude-code-query-engine` - QueryEngine port
4. `claude-code-permission-system` - Permission handling
5. `claude-code-state-management` - AppState + bootstrap state
6. `claude-code-context-collection` - System/user context
7. `claude-code-api-service` - Anthropic API client
8. `claude-code-mcp-service` - MCP client/server
9. `claude-code-lsp-service` - LSP manager
10. `claude-code-compact-service` - Context compression
11. `claude-code-plugin-system` - Plugin loader
12. `claude-code-skills-system` - Skill loading/execution
13. `claude-code-bridge-system` - IDE bridge
14. `claude-code-coordinator` - Multi-agent coordinator
15. `claude-code-memory-system` - Persistent memory
16. `eni-swarm-claude-integration` - ENI Swarm ↔ Claude Code integration

---

## Next Steps

1. ✅ Create all 16 skills above
2. ✅ Implement core infrastructure (tool.py, command.py, query_engine.py, permission.py, state.py)
3. ✅ Implement essential tools (bash, file_read, file_write, file_edit, glob, grep)
4. ✅ Implement advanced tools (task, agent, web, mcp/lsp)
5. ✅ Implement QueryEngine with tool loop
6. ✅ Implement 19 advanced commands
7. ✅ Implement services (API, MCP, LSP, Compact, Plugins)
8. ✅ Integrate with ENI Swarm master driver (eni_swarm_bridge.py)
9. ✅ Run full test suite (179/179 passing)
10. ✅ Hard bug test everything

---

## Critical Notes

- **TypeScript → Python**: Zod → Pydantic, async/await patterns preserved
- **React/Ink UI → Terminal**: Rich/TUI for dashboard, plain text for CLI
- **Bun APIs → Python**: `bun:bundle` feature flags → environment variables
- **Commander.js → Click/argparse**: CLI parsing
- **MCP SDK → Python MCP SDK**: Protocol compatibility
- **Anthropic SDK → Direct HTTP + OpenRouter**: Free router integration
- **Feature flags**: Map to `process.env` or config.yaml
- **ENI Swarm native**: AgentTool → Master Driver, SendMessageTool → FIFO, Coordinator → Orchestrator