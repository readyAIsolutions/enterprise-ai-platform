# ShellCommand: TypeScript → Python Implementation

## Source: `src/utils/ShellCommand.ts` → `hermes_cli/local_agent.py`

## Core Classes Mapped

### 1. ExecResult → CommandResponse
```python
# TypeScript:
type ExecResult = {
  stdout: string
  stderr: string
  code: number
  interrupted: boolean
  backgroundTaskId?: string
  outputFilePath?: string
  outputFileSize?: number
  outputTaskId?: string
  preSpawnError?: string
}

# Python (Pydantic):
class CommandResponse(BaseModel):
    stdout: str
    stderr: str
    returncode: int
    interrupted: bool = False
    background_task_id: Optional[str] = None
    output_file_path: Optional[str] = None
    output_file_size: Optional[int] = None
    output_task_id: Optional[str] = None
    pre_spawn_error: Optional[str] = None
```

### 2. ShellCommand Interface → ShellCommand Protocol
```python
# TypeScript:
type ShellCommand = {
  background: (taskId: string) => boolean
  result: Promise<ExecResult>
  kill: () => void
  status: 'running' | 'backgrounded' | 'completed' | 'killed'
  cleanup: () => void
  onTimeout?: (callback: (bgFn: (taskId: string) => boolean) => void) => void
  taskOutput: TaskOutput
}

# Python (Protocol):
class ShellCommand(Protocol):
    background: Callable[[str], bool]
    result: Awaitable[CommandResponse]
    kill: Callable[[], None]
    status: Literal['running', 'backgrounded', 'completed', 'killed']
    cleanup: Callable[[], None]
    on_timeout: Optional[Callable[[Callable[[str], bool]], None]]
    task_output: TaskOutput
```

### 3. ShellCommandImpl → ShellCommandImpl
```python
# Key implementation details:

class ShellCommandImpl:
    def __init__(
        self,
        child_process: asyncio.subprocess.Process,
        abort_signal: asyncio.Event,
        timeout: float,
        task_output: TaskOutput,
        should_auto_background: bool = False,
        max_output_bytes: int = 10_000_000
    ):
        # File mode: child stdout/stderr go to file fd (no StreamWrapper)
        # Pipe mode: StreamWrapper funnels to TaskOutput
        
        self._child_process = child_process
        self._abort_signal = abort_signal
        self._timeout = timeout
        self._should_auto_background = should_auto_background
        self._max_output_bytes = max_output_bytes
        self.task_output = task_output
        
        # StreamWrappers for pipe mode
        if child_process.stdout:
            self._stdout_wrapper = StreamWrapper(
                child_process.stdout, task_output, is_stderr=False
            )
        if child_process.stderr:
            self._stderr_wrapper = StreamWrapper(
                child_process.stderr, task_output, is_stderr=True
            )
        
        # Timeout handling with auto-background
        self._timeout_task = asyncio.create_task(self._timeout_handler())
        
        # Size watchdog for background file mode
        if should_auto_background and task_output.stdout_to_file:
            self._size_watchdog_task = asyncio.create_task(self._size_watchdog())
    
    async def _timeout_handler(self):
        await asyncio.sleep(self._timeout)
        if self._should_auto_background and self._on_timeout_callback:
            self._on_timeout_callback(self.background)
        else:
            self.kill()
    
    async def _size_watchdog(self):
        while self._status == 'backgrounded':
            await asyncio.sleep(5)  # SIZE_WATCHDOG_INTERVAL_MS
            try:
                size = os.path.getsize(self.task_output.path)
                if size > self._max_output_bytes:
                    self.kill()
                    break
            except OSError:
                pass  # File not yet created or deleted
    
    def background(self, task_id: str) -> bool:
        if self._status == 'running':
            self._background_task_id = task_id
            self._status = 'backgrounded'
            # Cancel foreground timeout
            self._timeout_task.cancel()
            # Start size watchdog for file mode
            if self.task_output.stdout_to_file:
                self._size_watchdog_task = asyncio.create_task(self._size_watchdog())
            return True
        return False
    
    def kill(self):
        self._status = 'killed'
        if self._child_process.pid:
            os.killpg(os.getpgid(self._child_process.pid), signal.SIGKILL)
        self._resolve_exit_code(137)  # SIGKILL
    
    def cleanup(self):
        # Cleanup stream wrappers, cancel tasks, release refs
        self._stdout_wrapper?.cleanup()
        self._stderr_wrapper?.cleanup()
        self.task_output.clear()
        self._timeout_task.cancel()
        self._size_watchdog_task?.cancel()
        self._child_process = None
        self._abort_signal = None
```

### 4. StreamWrapper → StreamReader Callback
```python
# TypeScript: StreamWrapper class wraps Readable stream
# Python: Use asyncio.StreamReader with callback

class StreamWrapper:
    def __init__(self, stream: asyncio.StreamReader, task_output: TaskOutput, is_stderr: bool):
        self._stream = stream
        self._task_output = task_output
        self._is_stderr = is_stderr
        self._task = asyncio.create_task(self._read_loop())
    
    async def _read_loop(self):
        while True:
            data = await self._stream.read(4096)
            if not data:
                break
            text = data.decode('utf-8', errors='replace')
            if self._is_stderr:
                self._task_output.write_stderr(text)
            else:
                self._task_output.write_stdout(text)
    
    def cleanup(self):
        self._task.cancel()
        self._stream = None
        self._task_output = None
```

### 5. TaskOutput → TaskOutput
```python
# File-backed output for large commands
class TaskOutput:
    def __init__(self, task_id: str, max_bytes: int = 10_000_000):
        self.task_id = task_id
        self.max_bytes = max_bytes
        self.path = f"/tmp/hermes-task-{task_id}.out"
        self._stdout_buffer = []
        self._stderr_buffer = []
        self._stdout_to_file = False
        self._fd = None
    
    def write_stdout(self, text: str):
        if self._stdout_to_file:
            os.write(self._fd, text.encode())
        else:
            self._stdout_buffer.append(text)
            if self._get_total_size() > self.max_bytes:
                self._spill_to_file()
    
    def _spill_to_file(self):
        self._fd = os.open(self.path, os.O_CREAT | os.O_WRONLY | os.O_APPEND)
        for chunk in self._stdout_buffer:
            os.write(self._fd, chunk.encode())
        self._stdout_buffer.clear()
        self._stdout_to_file = True
    
    async def get_stdout(self) -> str:
        if self._stdout_to_file:
            with open(self.path, 'r') as f:
                return f.read()
        return ''.join(self._stdout_buffer)
    
    def cleanup(self):
        if self._fd:
            os.close(self._fd)
        if os.path.exists(self.path):
            os.unlink(self.path)
```

### 6. wrapSpawn → wrap_spawn
```python
async def wrap_spawn(
    command: str,
    abort_signal: asyncio.Event,
    timeout: float,
    task_output: TaskOutput,
    should_auto_background: bool = False,
    max_output_bytes: int = 10_000_000,
    cwd: Optional[str] = None,
    env: Optional[dict] = None
) -> ShellCommand:
    """Spawn shell command and wrap in ShellCommand."""
    
    # Create subprocess
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE if not task_output.stdout_to_file else None,
        stderr=asyncio.subprocess.PIPE if not task_output.stdout_to_file else None,
        cwd=cwd,
        env={**os.environ, **(env or {})},
        preexec_fn=os.setsid if sys.platform != 'win32' else None,
        # For file mode, pass fd directly
        stdout=task_output._fd if task_output.stdout_to_file else asyncio.subprocess.PIPE,
        stderr=task_output._fd if task_output.stdout_to_file else asyncio.subprocess.PIPE,
    )
    
    return ShellCommandImpl(
        process, abort_signal, timeout, task_output,
        should_auto_background, max_output_bytes
    )
```

## Key Differences

| Aspect | TypeScript | Python |
|--------|------------|--------|
| Process kill | `tree-kill` (kills tree) | `os.killpg` (process group) |
| Stream handling | `StreamWrapper` class | `asyncio.StreamReader` + callback |
| File descriptors | `stdio: ['pipe', fd, fd]` | `stdout=fd, stderr=fd` in `create_subprocess_shell` |
| Timeout | `setTimeout` + `clearTimeout` | `asyncio.create_task` + `asyncio.sleep` |
| Abort handling | `AbortSignal` + event listener | `asyncio.Event` + `wait()` |
| Exit codes | 137 (SIGKILL), 143 (SIGTERM) | Same POSIX codes |

## Usage in Hermes

```python
# Direct usage
task_output = TaskOutput(generate_task_id('bash'))
shell_cmd = await wrap_spawn(
    "long_running_command",
    abort_signal=abort_signal,
    timeout=120,
    task_output=task_output,
    should_auto_background=True
)

# Wait for result
result = await shell_cmd.result
print(result.stdout, result.stderr, result.returncode)

# Or background it
shell_cmd.background("task-123")
# Later: get result from background task storage
```