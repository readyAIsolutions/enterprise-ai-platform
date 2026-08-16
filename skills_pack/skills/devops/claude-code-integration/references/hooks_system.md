# Hooks System: TypeScript → Python Implementation

## Source: `src/utils/hooks.ts` → `hermes_cli/hooks.py`

## Hook Events (from `src/types/hooks.ts`)

```python
# All hook events from Claude Code
HOOK_EVENTS = [
    # Tool lifecycle
    'PreToolUse',           # Before tool execution (can deny/modify)
    'PostToolUse',          # After successful tool execution
    'PostToolUseFailure',   # After failed tool execution
    'PermissionDenied',     # When user denies permission
    'PermissionRequest',    # When permission is requested
    
    # Session lifecycle
    'SessionStart',         # New session started
    'SessionEnd',           # Session ended
    'Stop',                 # User stopped agent
    'StopFailure',          # Stop failed
    
    # Compaction
    'PreCompact',           # Before context compaction
    'PostCompact',          # After context compaction
    
    # Configuration
    'ConfigChange',         # Config changed
    'CwdChanged',           # Working directory changed
    'FileChanged',          # File changed (watch)
    'InstructionsLoaded',   # CLAUDE.md loaded
    
    # Subagent
    'SubagentStart',        # Subagent spawned
    'SubagentStop',         # Subagent stopped
    'TaskCreated',          # Background task created
    'TaskCompleted',        # Background task done
    
    # Elicitation (user input)
    'Elicitation',          # Ask user for input
    'ElicitationResult',    # User provided input
    
    # Special
    'Setup',                # Initial setup
    'TeammateIdle',         # Teammate idle (multi-user)
    'Notification',         # User notification
    'UserPromptSubmit',     # User submitted prompt
]
```

## Hook Configuration (from `settings/types.ts`)

```python
# Hook matcher configuration
class HookMatcher(BaseModel):
    matcher: str              # Glob pattern for tool names (e.g., "Bash", "Edit", "*")
    hooks: List[HookCommand]  # Commands to execute

class HookCommand(BaseModel):
    type: Literal['command']  # Currently only 'command' supported
    command: str              # Shell command to execute
    timeout: int = 30000      # Timeout in milliseconds
    env: Dict[str, str] = {}  # Additional environment variables

# Example configuration:
hooks_config = {
    "PreToolUse": [
        {"matcher": "Bash", "hooks": [
            {"type": "command", "command": "echo 'Running bash: $TOOL_INPUT'", "timeout": 5000}
        ]},
        {"matcher": "Edit|Write", "hooks": [
            {"type": "command", "command": "./scripts/validate.sh", "timeout": 10000}
        ]}
    ],
    "PostToolUse": [
        {"matcher": "*", "hooks": [
            {"type": "command", "command": "echo 'Tool completed: $TOOL_NAME'", "timeout": 2000}
        ]}
    ]
}
```

## Hook Input/Output Schemas

### PreToolUse
```python
# Input (available as environment variables):
class PreToolUseInput(BaseModel):
    tool_name: str
    tool_input: Dict[str, Any]  # Full tool input

# Output (JSON to stdout):
class HookCallback(BaseModel):
    # For sync hooks: immediate decision
    behavior: Literal['allow', 'deny'] = 'allow'
    message: Optional[str] = None          # Show to user
    tool_input: Optional[Dict] = None      # Modified input (allow only)
    stop_reason: Optional[str] = None      # Stop agent with reason
    
    # For async hooks: deferred response
    async: bool = False
    async_id: Optional[str] = None         # For matching response
```

### PostToolUse
```python
class PostToolUseInput(BaseModel):
    tool_name: str
    tool_input: Dict[str, Any]
    tool_output: str  # Tool result
    tool_use_id: str

class PostToolUseOutput(BaseModel):
    # Usually just logs/metrics, but can modify output
    behavior: Literal['allow', 'deny'] = 'allow'
    tool_output: Optional[str] = None  # Modified output
```

### UserPromptSubmit
```python
class UserPromptSubmitInput(BaseModel):
    prompt: str
    session_id: str

class UserPromptSubmitOutput(BaseModel):
    behavior: Literal['allow', 'deny'] = 'allow'
    prompt: Optional[str] = None  # Modified prompt
    additional_context: Optional[str] = None  # Extra context for agent
```

## Implementation: HooksManager

```python
import asyncio
import os
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

@dataclass
class HookResult:
    success: bool
    output: Optional[Dict] = None
    error: Optional[str] = None

class HooksManager:
    def __init__(self, config_path: str = "~/.hermes/hooks.yaml"):
        self.config = self._load_config(config_path)
        self.async_hooks: Dict[str, asyncio.Future] = {}
    
    def _load_config(self, path: str) -> Dict:
        # Load hooks from config.yaml
        pass
    
    async def execute_hook(
        self,
        event: str,
        input_data: Dict,
        timeout: int = 30000
    ) -> HookResult:
        """Execute all hooks for an event."""
        matchers = self.config.get(event, [])
        results = []
        
        for matcher in matchers:
            if not self._match_tool(matcher.matcher, input_data.get('tool_name', '')):
                continue
            
            for hook in matcher.hooks:
                result = await self._execute_command(hook, input_data, timeout)
                results.append(result)
                
                # For PreToolUse: check for deny/stop
                if event == 'PreToolUse' and result.output:
                    behavior = result.output.get('behavior', 'allow')
                    if behavior == 'deny':
                        return HookResult(success=False, output=result.output)
                    if behavior == 'stop':
                        return HookResult(success=False, output={'stop': True, 'reason': result.output.get('stop_reason')})
        
        # Merge results (last wins for modifications)
        merged = {}
        for r in results:
            if r.output:
                merged.update(r.output)
        
        return HookResult(success=True, output=merged if merged else None)
    
    async def _execute_command(
        self,
        hook: HookCommand,
        input_data: Dict,
        timeout: int
    ) -> HookResult:
        # Prepare environment
        env = {**os.environ, **hook.env}
        # Add hook-specific vars
        env.update({
            'HOOK_EVENT': event,
            'TOOL_NAME': input_data.get('tool_name', ''),
            'TOOL_INPUT': json.dumps(input_data.get('tool_input', {})),
            'TOOL_OUTPUT': input_data.get('tool_output', ''),
            'SESSION_ID': input_data.get('session_id', ''),
        })
        
        try:
            proc = await asyncio.create_subprocess_shell(
                hook.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                preexec_fn=os.setsid if sys.platform != 'win32' else None
            )
            
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout / 1000
            )
            
            if proc.returncode != 0:
                return HookResult(success=False, error=stderr.decode())
            
            # Parse JSON output for sync hooks
            output_text = stdout.decode().strip()
            if output_text:
                try:
                    return HookResult(success=True, output=json.loads(output_text))
                except json.JSONDecodeError:
                    return HookResult(success=True, output={'message': output_text})
            
            return HookResult(success=True)
            
        except asyncio.TimeoutError:
            return HookResult(success=False, error=f"Hook timed out after {timeout}ms")
        except Exception as e:
            return HookResult(success=False, error=str(e))
    
    def _match_tool(self, pattern: str, tool_name: str) -> bool:
        # Support glob patterns: "Bash", "Edit|Write", "*"
        import fnmatch
        for p in pattern.split('|'):
            if fnmatch.fnmatch(tool_name, p.strip()):
                return True
        return False


# Async Hook Support
class AsyncHookRegistry:
    """Registry for async hooks that respond later via callback."""
    
    def __init__(self):
        self.pending: Dict[str, asyncio.Future] = {}
    
    def register(self, async_id: str) -> asyncio.Future:
        future = asyncio.Future()
        self.pending[async_id] = future
        return future
    
    def resolve(self, async_id: str, result: Dict):
        if async_id in self.pending:
            self.pending[async_id].set_result(result)
            del self.pending[async_id]
    
    def reject(self, async_id: str, error: str):
        if async_id in self.pending:
            self.pending[async_id].set_exception(Exception(error))
            del self.pending[async_id]
    
    async def wait_for(self, async_id: str, timeout: float = 300) -> Dict:
        future = self.pending.get(async_id)
        if not future:
            raise ValueError(f"No pending async hook: {async_id}")
        return await asyncio.wait_for(future, timeout=timeout)


# Session End Hooks (tight timeout)
SESSION_END_HOOK_TIMEOUT_MS = 1500

async def execute_session_end_hooks(session_id: str):
    """Execute SessionEnd hooks with strict timeout."""
    hooks = config.get('SessionEnd', [])
    tasks = []
    
    for hook in hooks:
        task = asyncio.create_task(
            execute_command_with_timeout(hook, timeout=SESSION_END_HOOK_TIMEOUT_MS / 1000)
        )
        tasks.append(task)
    
    # Wait for all with overall timeout
    try:
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=1.5)
    except asyncio.TimeoutError:
        pass  # Session end hooks must not block shutdown


# Hook Execution Order (from hooks.ts):
# 1. Discover hooks from config (user + managed + project)
# 2. Filter by matcher
# 3. For sync hooks: execute sequentially, merge outputs
# 4. For async hooks: register, fire-and-forget, wait for callback
# 5. Apply merged output (deny/allow/modify)
```

## Environment Variables Passed to Hooks

```python
# All hooks receive:
HOOK_ENV_VARS = {
    'HOOK_EVENT',           # Event name
    'HOOK_MATCHER',         # Matcher pattern that matched
    'SESSION_ID',           # Current session ID
    'CWD',                  # Current working directory
    
    # Tool-specific:
    'TOOL_NAME',
    'TOOL_INPUT',           # JSON
    'TOOL_OUTPUT',
    'TOOL_USE_ID',
    
    # UserPromptSubmit:
    'USER_PROMPT',
    
    # SessionStart/End:
    'SESSION_START_TIME',
    
    # Subagent:
    'SUBAGENT_NAME',
    'SUBAGENT_TYPE',
    'SUBAGENT_DESCRIPTION',
}
```

## Permission Hooks (Special)

```python
# PermissionRequest / PermissionDenied hooks
# These can modify the permission decision

class PermissionHookOutput(BaseModel):
    behavior: Literal['allow', 'deny', 'ask'] = 'ask'
    message: Optional[str] = None
    allow_for_session: bool = False  # Remember for session

# Example: Auto-allow safe commands
# hooks.yaml:
#   PermissionRequest:
#     - matcher: "Bash"
#       hooks:
#         - command: |
#             if [[ "$TOOL_INPUT" =~ ^(ls|cat|head|tail|grep|find) ]]; then
#               echo '{"behavior": "allow", "allow_for_session": true}'
#             else
#               echo '{"behavior": "ask"}'
#             fi
```

## Integration with Hermes

```python
# In agent loop (agent_loop.py):

class AgentLoop:
    def __init__(self):
        self.hooks = HooksManager()
    
    async def execute_tool(self, tool_call: ToolCall) -> ToolResult:
        # PreToolUse hook
        hook_result = await self.hooks.execute_hook('PreToolUse', {
            'tool_name': tool_call.name,
            'tool_input': tool_call.input,
            'session_id': self.session_id
        })
        
        if not hook_result.success:
            return ToolResult(error=f"Hook error: {hook_result.error}")
        
        if hook_result.output:
            behavior = hook_result.output.get('behavior', 'allow')
            if behavior == 'deny':
                return ToolResult(error=hook_result.output.get('message', 'Denied by hook'))
            if behavior == 'stop':
                raise StopAgent(hook_result.output.get('stop_reason', 'Hook stop'))
            if 'tool_input' in hook_result.output:
                tool_call.input = hook_result.output['tool_input']
        
        # Execute tool
        result = await self._execute_tool(tool_call)
        
        # PostToolUse hook
        await self.hooks.execute_hook('PostToolUse', {
            'tool_name': tool_call.name,
            'tool_input': tool_call.input,
            'tool_output': result.output,
            'tool_use_id': tool_call.id,
            'session_id': self.session_id
        })
        
        return result
```