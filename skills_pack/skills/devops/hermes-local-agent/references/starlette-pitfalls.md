# Starlette/FastAPI Pitfalls Discovered During Dashboard Build

## 1. Jinja2Templates Cache Bug

**Symptom:** `TypeError: cannot use 'tuple' as a dict key (unhashable type: 'dict')`

**Root cause:** Starlette's `Jinja2Templates` has a cache bug where it uses a tuple containing a dict as a cache key, which is unhashable. This triggers when multiple requests render templates in the same process.

**Fix:** Bypass `Jinja2Templates` entirely. Use `jinja2.Environment` directly:

```python
from jinja2 import Environment, FileSystemLoader

jinja_env = Environment(loader=FileSystemLoader("templates/"), autoescape=True)

# In route handler:
template = jinja_env.get_template("page.html")
return HTMLResponse(template.render(context))
```

Replace ALL instances of:
```python
from starlette.templating import Jinja2Templates
templates = Jinja2Templates(directory=str(TEMPLATES))
return templates.TemplateResponse("page.html", ctx)
```

**Hit in:** Blog server, dashboard server. Multiple agents encountered this independently.

## 2. asyncio.run() Cannot Be Called From Running Event Loop

**Symptom:** `RuntimeError: asyncio.run() cannot be called from a running event loop`

**Root cause:** Calling `asyncio.run()` inside an async Starlette route handler. Starlette runs routes in an asyncio event loop. `asyncio.run()` creates a new event loop, which is illegal.

**Fix:** Make the called function async and `await` it instead:

```python
# BROKEN:
async def handler(request):
    result = asyncio.run(my_async_function())  # RuntimeError

# FIXED:
async def handler(request):
    result = await my_async_function()  # Works
```

If the function is defined as `async def`, always call it with `await`, never with `asyncio.run()`.

## 3. Python Package Requires __init__.py for Subpackage Imports

**Symptom:** `ModuleNotFoundError: No module named 'enterprise.modules'`

**Root cause:** `enterprise/modules/` directory existed but had no `__init__.py`. Python doesn't treat directories without `__init__.py` as packages (even in Python 3.14 with implicit namespace packages, explicit __init__.py is needed for subpackage resolution in some cases).

**Fix:** `touch enterprise/modules/__init__.py`

Also needed for `enterprise/__init__.py` if `from enterprise.modules.xxx import ...` is used.

## 4. Starlette Background Process Output Capture

**Symptom:** Zero stdout from uvicorn/Starlette processes started with `terminal(background=true)`. Print statements with `flush=True` produce no output.

**Root cause:** uvicorn captures all stdout and routes it through its logging system. Print statements before `uvicorn.run()` go to stdout but after uvicorn starts, they're swallowed.

**Fix:** Use uvicorn's logger or add startup info in route handlers. For debugging inside Starlette, expose a `/debug` endpoint that returns `sys.path`, import errors, and tracebacks as JSON.

## 5. Import-Time Enterprise Module Loading Fails Under Uvicorn

**Symptom:** Enterprise modules import fine from `python3 -c "..."` but fail with `ModuleNotFoundError` when loaded via uvicorn.

**Root cause:** Uvicorn worker processes may not inherit the parent's `sys.path`. Module-level `sys.path.insert()` runs at import time, but uvicorn's import mechanism may use a different import context.

**Fix two-pronged:**
1. Hard-code the project root path: `sys.path.insert(0, "/home/hunter/Desktop/Enterprise Builder")`
2. Re-insert the path inside every route handler that does enterprise imports
3. Use lazy imports — don't import enterprise modules at module level, import them inside async functions

## 6. Multiple Project Roots (Eni Builder vs Enterprise Builder)

**Symptom:** `enterprise/` exists at both `/home/hunter/Desktop/Eni Builder/` and `/home/hunter/Desktop/Enterprise Builder/`. One is stale, one has the real modules.

**Fix:** Check which path has `enterprise/platform_kernel.py` or `enterprise/modules/` and use that one. Hard-code the canonical path rather than relying on relative resolution.
