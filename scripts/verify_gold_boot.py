"""Verify the two new gold modules (memory, mcp_tools) boot via the real PlatformOS path."""
import asyncio
import importlib
from pathlib import Path
from enterprise.platform_kernel import PlatformOS

def import_all_modules() -> list[str]:
    """Import each enterprise.modules.<name> package so @module decorators register."""
    import enterprise.modules as mpkg
    mpkg_dir = Path(mpkg.__file__).parent
    imported = []
    for entry in sorted(mpkg_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("_"):
            continue
        if not (entry / "__init__.py").exists():
            continue
        try:
            importlib.import_module(f"enterprise.modules.{entry.name}")
            imported.append(entry.name)
        except Exception as e:  # pragma: no cover
            print(f"  (import failed for {entry.name}: {e})")
    return imported

async def main():
    base = Path(__file__).resolve().parent.parent
    imported = import_all_modules()
    print(f"IMPORTED MODULE PACKAGES ({len(imported)}): {', '.join(imported)}")

    PlatformOS.reset_instance()
    os = PlatformOS.instance()
    os.initialize(config_path=Path(base / "config.yaml"))
    await os.start()

    reg = os._module_registry
    names = sorted({r.name for r in reg.list_modules()})
    healthy = {r.name: r.instance for r in reg.list_modules() if r.instance is not None}
    print(f"DISCOVERED ({len(names)}): {', '.join(names)}")
    print(f"STATE: {os._state}")
    print(f"INITIALIZED INSTANCES ({len(healthy)}): {', '.join(sorted(healthy))}")
    assert "memory" in names, "memory NOT discovered!"
    assert "mcp_tools" in names, "mcp_tools NOT discovered!"
    assert "memory" in healthy, "memory NOT initialized!"
    assert "mcp_tools" in healthy, "mcp_tools NOT initialized!"
    print("MEMORY instance: OK")
    print("MCP_TOOLS instance: OK")

    # Functional smoke on the live instances
    mem_mod = healthy["memory"]
    entry = mem_mod.remember("u1", "Hunter prefers black and white terminals")
    hits = mem_mod.search("terminal color preference", user_id="u1", k=1)
    print(f"MEMORY smoke: stored {entry.id}, top hit={hits[0].memory.content[:40] if hits else 'NONE'}")

    mcp_mod = healthy["mcp_tools"]
    tools = mcp_mod.list_tools()
    print(f"MCP smoke: {len(tools)} tools, first={tools[0]['name'] if tools else 'NONE'}")
    res = mcp_mod.call_tool("add", {"a": 2, "b": 3})
    print(f"MCP smoke: add(2,3) = {res}")

    await os.shutdown()
    print("GOLD BOOT VERIFY PASS")

asyncio.run(main())
