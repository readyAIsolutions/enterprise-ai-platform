# Client Execution Reference

## Capability Detection (on startup)

```python
def detect_capabilities() -> ClientCapabilities:
    caps = ClientCapabilities()
    
    # CPU / RAM
    caps.cpu_cores = os.cpu_count() or 1
    caps.ram_gb = round(psutil.virtual_memory().total / (1024**3), 1)
    
    # GPU detection
    # NVIDIA
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            caps.gpu = True
            caps.gpu_name = result.stdout.strip().split("\n")[0]
            caps.tags.append("cuda")
    except Exception:
        pass
    
    # AMD/ROCm
    try:
        result = subprocess.run(["rocminfo"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and "gfx" in result.stdout.lower():
            caps.gpu = True
            caps.gpu_name = caps.gpu_name or "AMD GPU"
            caps.tags.append("rocm")
    except Exception:
        pass
    
    # Python / Hermes
    caps.python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    try:
        result = subprocess.run(["hermes", "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            caps.hermes_version = result.stdout.strip()
    except Exception:
        pass
    
    # Local LLM backends
    if shutil.which("ollama"):
        caps.tags.append("ollama")
        caps.models.extend(["ollama:llama3.1", "ollama:codellama", "ollama:mistral"])
    if Path("/home/hunter/.local/bin/llama-server").exists() or shutil.which("llama-server"):
        caps.tags.append("llama.cpp")
    
    # Always available if Hermes configured
    if "free-router" not in caps.providers:
        caps.providers.append("free-router")
    caps.tags.append("free-router")
    
    caps.max_concurrent_tasks = MAX_CONCURRENT
    caps.tags.append(f"cpu-{caps.cpu_cores}")
    if caps.gpu:
        caps.tags.append("gpu")
    
    return caps
```

## API Key Loading Priority

```python
def load_api_keys() -> Dict[str, str]:
    keys = {}
    
    # 1. Environment variables (highest priority)
    env_mapping = {
        "openrouter": "OPENROUTER_API_KEY",
        "zhipu": "ZHIPU_API_KEY",
        "sambanova": "SAMBANOVA_API_KEY",
        "cerebras": "CEREBRAS_API_KEY",
        "nvidia": "NVIDIA_API_KEY",
        "upstage": "UPSTAGE_API_KEY",
        "deepinfra": "DEEPINFRA_API_KEY",
        "cohere": "COHERE_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "xai": "XAI_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "groq": "GROQ_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "moonshot": "MOONSHOT_API_KEY",
        "replicate": "REPLICATE_API_TOKEN",
        "fireworks": "FIREWORKS_API_KEY",
        "huggingface": "HUGGINGFACE_API_KEY",
        "cloudflare": "CLOUDFLARE_API_TOKEN",
        "runpod": "RUNPOD_API_KEY",
        "vastai": "VASTAI_API_KEY",
    }
    
    for provider, env_var in env_mapping.items():
        val = os.environ.get(env_var)
        if val:
            keys[provider] = val
    
    # 2. Hermes config.yaml
    hermes_config = Path.home() / ".hermes" / "config.yaml"
    if hermes_config.exists():
        try:
            import yaml
            with open(hermes_config) as f:
                cfg = yaml.safe_load(f)
            for name, pcfg in cfg.get("providers", {}).items():
                if name not in keys and pcfg.get("api_key"):
                    keys[name] = pcfg["api_key"]
        except Exception:
            pass
    
    # 3. Local Creed keys file
    keys_file = Path.home() / ".creed" / "api_keys.json"
    if keys_file.exists():
        try:
            with open(keys_file) as f:
                local_keys = json.load(f)
            for k, v in local_keys.items():
                if k not in keys:
                    keys[k] = v
        except Exception:
            pass
    
    return keys
```

## Hermes Execution with Injected Keys

```python
async def execute_task(task: TaskSpec) -> TaskResult:
    workdir = Path(task.workdir).expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    
    # Build prompt with protocol
    prompt = build_prompt(task)
    
    # Prepare environment with ALL client keys + task-specific keys
    env = os.environ.copy()
    
    # Task-specific keys (from server, injected via metadata)
    for provider, key in task.metadata.get("_client_api_keys", {}).items():
        env_var = provider_to_env(provider)
        if env_var:
            env[env_var] = key
    
    # Fallback: all client keys
    for provider, key in self.api_keys.items():
        env_var = provider_to_env(provider)
        if env_var and env_var not in env:
            env[env_var] = key
    
    # Execute
    cmd = [
        HERMES_BIN, "-z", prompt,
        "-m", task.model,
        "--provider", task.provider,
        "--yolo",
    ]
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(workdir),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        limit=1024*1024,
    )
    
    # Stream output + progress
    stdout_lines = []
    async for line in proc.stdout:
        line = line.decode(errors="replace").rstrip()
        stdout_lines.append(line)
        if len(stdout_lines) % 10 == 0:
            await send_progress(task.task_id, 0.5, line[:200])
    
    exit_code = await asyncio.wait_for(proc.wait(), timeout=task.timeout_seconds)
    
    # Collect artifacts
    artifacts = collect_artifacts(workdir, task.artifacts_expected)
    
    return TaskResult(
        task_id=task.task_id,
        client_id=self.client_id,
        success=(exit_code == 0),
        exit_code=exit_code,
        stdout="\n".join(stdout_lines),
        stderr="",
        artifacts=artifacts,
        duration_seconds=time.time() - start_time,
        error="" if exit_code == 0 else "\n".join(stdout_lines[-20:]),
    )
```

## Provider → Environment Variable Mapping

```python
def provider_to_env(provider: str) -> Optional[str]:
    mapping = {
        "openrouter": "OPENROUTER_API_KEY",
        "zhipu": "ZHIPU_API_KEY",
        "sambanova": "SAMBANOVA_API_KEY",
        "cerebras": "CEREBRAS_API_KEY",
        "nvidia": "NVIDIA_API_KEY",
        "upstage": "UPSTAGE_API_KEY",
        "deepinfra": "DEEPINFRA_API_KEY",
        "cohere": "COHERE_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "xai": "XAI_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "groq": "GROQ_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "moonshot": "MOONSHOT_API_KEY",
        "replicate": "REPLICATE_API_TOKEN",
        "fireworks": "FIREWORKS_API_KEY",
        "huggingface": "HUGGINGFACE_API_KEY",
        "cloudflare": "CLOUDFLARE_API_TOKEN",
        "runpod": "RUNPOD_API_KEY",
        "vastai": "VASTAI_API_KEY",
        "free-router": "OPENROUTER_API_KEY",  # free-router uses OpenRouter
    }
    return mapping.get(provider.lower())
```

## Artifact Collection

```python
def collect_artifacts(workdir: Path, patterns: List[str]) -> List[Dict]:
    artifacts = []
    for pattern in patterns:
        for file_path in workdir.rglob(pattern):
            if file_path.is_file():
                try:
                    stat = file_path.stat()
                    with open(file_path, "rb") as f:
                        content = f.read()
                    file_hash = hashlib.blake2b(content).hexdigest()[:16]
                    artifacts.append({
                        "path": str(file_path.relative_to(workdir)),
                        "size": stat.st_size,
                        "hash": file_hash,
                        "mtime": stat.st_mtime,
                        "stored_path": str(file_path),  # For upload
                    })
                except Exception:
                    pass
    return artifacts
```

## Upload Format

```python
async def upload_artifacts(task_id: str, artifacts: List[Dict]):
    upload_artifacts = []
    for art in artifacts:
        stored = art.get("stored_path")
        if stored and Path(stored).exists():
            async with aiofiles.open(stored, "rb") as f:
                content = await f.read()
            art_copy = art.copy()
            art_copy["content"] = base64.b64encode(content).decode()
            upload_artifacts.append(art_copy)
        else:
            upload_artifacts.append(art)
    
    if upload_artifacts:
        msg = msg_artifact_upload(task_id, self.client_id, upload_artifacts)
        await self.ws.send_bytes(encode(msg))
```

## Common Pitfalls

| Issue | Cause | Fix |
|-------|-------|-----|
| `hermes` not found | `HERMES_BIN` wrong or not in PATH | Set `CREED_HERMES_BIN` or ensure `hermes` in PATH |
| API key not working | Key loaded but not passed to subprocess | Check `provider_to_env()` mapping includes provider |
| Artifact upload fails | File too large for WS frame | Increase `max_message_size` or chunk large files |
| Task timeout | Default 600s too short | Set `timeout_seconds` in task spec |
| GPU not detected | `nvidia-smi` not in PATH | Install nvidia-utils or add to PATH |
| Hermes exits immediately | Missing `--yolo` flag or auth | Ensure `--yolo` passed and keys in env |