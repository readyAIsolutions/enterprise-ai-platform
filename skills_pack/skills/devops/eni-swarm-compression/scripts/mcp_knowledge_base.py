#!/usr/bin/env python3
"""
MCP Knowledge Base Server - Exposes ENI skills, memories, references as MCP resources
Run: python3 -m mcp_servers.knowledge_base
"""
import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, Tool, TextContent

app = Server("eni-knowledge-base")

SKILLS_DIR = Path("/home/hunter/.hermes/skills")
MEMORY_FILE = Path("/home/hunter/.hermes/memories/memory.json")
REFERENCES_BASE = Path("/home/hunter/.hermes/skills/devops/eni-swarm-content-gen/references")

@app.list_resources()
async def list_resources() -> List[Resource]:
    resources = []
    
    # Skills
    for skill_dir in SKILLS_DIR.iterdir():
        if skill_dir.is_dir():
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                resources.append(Resource(
                    uri=f"eni://skill/{skill_dir.name}",
                    name=f"Skill: {skill_dir.name}",
                    description=skill_md.read_text()[:200],
                    mimeType="text/markdown"
                ))
    
    # Memories
    if MEMORY_FILE.exists():
        resources.append(Resource(
            uri="eni://memory/main",
            name="Hermes Memory",
            description="Persistent memory across sessions",
            mimeType="application/json"
        ))
    
    # References
    for ref_file in REFERENCES_BASE.glob("*.md"):
        resources.append(Resource(
            uri=f"eni://reference/{ref_file.stem}",
            name=f"Reference: {ref_file.stem}",
            description=ref_file.read_text()[:200],
            mimeType="text/markdown"
        ))
    
    return resources

@app.read_resource()
async def read_resource(uri: str) -> str:
    if uri.startswith("eni://skill/"):
        skill_name = uri.replace("eni://skill/", "")
        skill_md = SKILLS_DIR / skill_name / "SKILL.md"
        if skill_md.exists():
            return skill_md.read_text()
    
    elif uri == "eni://memory/main":
        if MEMORY_FILE.exists():
            return MEMORY_FILE.read_text()
        return "{}"
    
    elif uri.startswith("eni://reference/"):
        ref_name = uri.replace("eni://reference/", "")
        ref_file = REFERENCES_BASE / f"{ref_name}.md"
        if ref_file.exists():
            return ref_file.read_text()
    
    raise ValueError(f"Unknown resource: {uri}")

@app.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="search_skills",
            description="Search skills by keyword",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            }
        ),
        Tool(
            name="read_memory",
            description="Read a specific memory entry",
            inputSchema={
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"]
            }
        ),
        Tool(
            name="get_reference",
            description="Get a reference document by name",
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"]
            }
        ),
    ]

@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    if name == "search_skills":
        query = arguments["query"].lower()
        results = []
        for skill_dir in SKILLS_DIR.iterdir():
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                content = skill_md.read_text().lower()
                if query in content:
                    results.append({"name": skill_dir.name, "path": str(skill_md)})
        return [TextContent(type="text", text=json.dumps(results, indent=2))]
    
    elif name == "read_memory":
        key = arguments["key"]
        if MEMORY_FILE.exists():
            data = json.loads(MEMORY_FILE.read_text())
            return [TextContent(type="text", text=json.dumps(data.get(key, {}), indent=2))]
        return [TextContent(type="text", text="{}")]
    
    elif name == "get_reference":
        ref_name = arguments["name"]
        ref_file = REFERENCES_BASE / f"{ref_name}.md"
        if ref_file.exists():
            return [TextContent(type="text", text=ref_file.read_text())]
        return [TextContent(type="text", text=f"Reference not found: {ref_name}")]
    
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())