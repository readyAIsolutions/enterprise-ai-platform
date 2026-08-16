# Building FastAPI/Starlette Apps with Enterprise Modules

Recipe for building web apps that integrate live enterprise platform data.

## Architecture

Any app that displays platform data should:
1. **Import ALL available modules** — PlatformOS, EventBus, KnowledgeGraph, ResearchPlanner, CompressionBridge, ValidationEngine, SwarmNetwork
2. **Display the LIVE score** on every page — call `run_full_validation()` and show `final_score` and `certification`
3. **Never hardcode scores** — the validation engine is the source of truth
4. **Dark terminal theme** — LO prefers black background (#000), white text, grayscale, monospace fonts

## Import Pattern

```python
# enterprise.platform_kernel
from enterprise.platform_kernel import PlatformOS, EventBus, Event

# enterprise.modules.*
from enterprise.modules.knowledge_graph import Entity, EntityType, EntityRegistry
from enterprise.modules.research_verification import ResearchPlanner
from enterprise.modules.compression_bridge import CompressionBridge
from enterprise.modules.enterprise_validation import run_full_validation
from enterprise.modules.swarm_network import SwarmNetworkBridge, WiFiReader
```

## Startup Banner

Print a boot banner showing the live platform score:
```python
validation = get_cached_validation()
score = validation.get("final_score", "?")
cert = validation.get("certification", "?")
print(f"  Platform Score: {score} — {cert}")
```

## Jinja2Templates Bypass

On Python 3.14 + Starlette/FastAPI, `Jinja2Templates` crashes:
```
TypeError: cannot use 'tuple' as a dict key (unhashable type: 'dict')
```

Fix: use `jinja2.Environment` directly:
```python
from jinja2 import Environment, FileSystemLoader
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

def render_template(name, context):
    template = jinja_env.get_template(name)
    return HTMLResponse(template.render(context))
```

## Subprocess Validation (Recommended)

When direct import causes issues (event loop, path, singleton deadlocks):
```python
import subprocess, json

def _run_validation():
    result = subprocess.run(
        [sys.executable, "run_validation.py"],
        capture_output=True, text=True, timeout=30,
        cwd="/home/hunter/Desktop/Enterprise Builder"
    )
    return json.loads(result.stdout) if result.returncode == 0 else None
```

## Port Assignment

- Dashboard: **8421**
- Blog: **8422**
- ENI Swarm Dashboard: **8420**
- Turbocharger: **8922**
- Free Router: **8920**

## Blog Architecture

The blog at `/home/hunter/Desktop/Eni Builder/blog/` demonstrates the pattern:
- `server.py` — FastAPI on :8422, imports all 6 enterprise modules
- `templates/` — 7 Jinja2 templates (base, index, post, health, status, knowledge, about)
- `static/style.css` — dark terminal theme, 559 lines
- `posts/` — 5 markdown posts about the platform

Routes: `/`, `/post/{slug}`, `/health`, `/status`, `/knowledge`, `/about`, `/api/stats`, `/api/posts`, `/api/health`
