"""
MCP Knowledge Base Server
=========================
Exposes ENI skills, memories, and project state as MCP resources/tools.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

try:
    from mcp.server import Server
    from mcp.types import Resource, Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

SKILLS_DIR = Path("/home/hunter/.hermes/skills")
MEMORIES_DIR = Path("/home/hunter/.hermes/memories")
ENI_SWARM_DIR = Path("/home/hunter/Commander/eni_swarm")


def list_skills() -> List[Dict[str, str]]:
    skills = []
    if SKILLS_DIR.exists():
        for skill_dir in SKILLS_DIR.iterdir():
            if skill_dir.is_dir():
                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists():
                    skills.append({"name": skill_dir.name, "path": str(skill_md)})
    return skills


def read_skill(name: str) -> str:
    skill_md = SKILLS_DIR / name / "SKILL.md"
    return skill_md.read_text() if skill_md.exists() else ""


def list_memories() -> List[str]:
    if MEMORIES_DIR.exists():
        return [f.stem for f in MEMORIES_DIR.glob("*.md")]
    return []


def read_memory(category: str) -> str:
    mem_file = MEMORIES_DIR / f"{category}.md"
    return mem_file.read_text() if mem_file.exists() else ""


def list_status_files() -> List[Dict[str, str]]:
    statuses = []
    if ENI_SWARM_DIR.exists():
        for f in ENI_SWARM_DIR.glob("STATUS_*.md"):
            statuses.append({"name": f.stem, "path": str(f), "mtime": f.stat().st_mtime})
    return statuses


def read_status(name: str) -> str:
    f = ENI_SWARM_DIR / f"STATUS_{name}.md"
    if not f.exists():
        f = ENI_SWARM_DIR / f"{name}.md"
    return f.read_text() if f.exists() else ""


if MCP_AVAILABLE:
    app = Server("eni-knowledge-base")

    @app.list_resources()
    async def list_resources() -> List[Resource]:
        resources = []
        for skill in list_skills():
            resources.append(Resource(
                uri=f"eni://skill/{skill['name']}",
                name=f"Skill: {skill['name']}",
                description=f"ENI skill: {skill['name']}",
                mimeType="text/markdown",
            ))
        for mem in list_memories():
            resources.append(Resource(
                uri=f"eni://memory/{mem}",
                name=f"Memory: {mem}",
                description=f"ENI durable memory: {mem}",
                mimeType="text/markdown",
            ))
        for st in list_status_files():
            resources.append(Resource(
                uri=f"eni://status/{st['name']}",
                name=f"Status: {st['name']}",
                description=f"ENI swarm status: {st['name']}",
                mimeType="text/markdown",
            ))
        return resources

    @app.read_resource()
    async def read_resource(uri: str) -> str:
        if uri.startswith("eni://skill/"):
            name = uri.split("/")[-1]
            return read_skill(name)
        elif uri.startswith("eni://memory/"):
            cat = uri.split("/")[-1]
            return read_memory(cat)
        elif uri.startswith("eni://status/"):
            name = uri.split("/")[-1]
            return read_status(name)
        raise ValueError(f"Unknown resource: {uri}")

    @app.list_tools()
    async def list_tools() -> List[Tool]:
        return [
            Tool(
                name="list_skills",
                description="List all ENI skills",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="read_skill",
                description="Read an ENI skill by name",
                inputSchema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
            ),
            Tool(
                name="list_memories",
                description="List all ENI memory categories",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="read_memory",
                description="Read an ENI memory category",
                inputSchema={"type": "object", "properties": {"category": {"type": "string"}}, "required": ["category"]},
            ),
            Tool(
                name="list_status",
                description="List all ENI swarm status files",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="read_status",
                description="Read an ENI swarm status file",
                inputSchema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
            ),
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        if name == "list_skills":
            return [TextContent(type="text", text=json.dumps(list_skills(), indent=2))]
        elif name == "read_skill":
            return [TextContent(type="text", text=read_skill(arguments["name"]))]
        elif name == "list_memories":
            return [TextContent(type="text", text=json.dumps(list_memories(), indent=2))]
        elif name == "read_memory":
            return [TextContent(type="text", text=read_memory(arguments["category"]))]
        elif name == "list_status":
            return [TextContent(type="text", text=json.dumps(list_status_files(), indent=2))]
        elif name == "read_status":
            return [TextContent(type="text", text=read_status(arguments["name"]))]
        raise ValueError(f"Unknown tool: {name}")


def main():
    import sys
    if not MCP_AVAILABLE:
        print("MCP not installed. Install with: pip install mcp")
        sys.exit(1)

    # Run as stdio server
    import anyio
    from mcp.server.stdio import stdio_server

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())

    anyio.run(run)


if __name__ == "__main__":
    main()