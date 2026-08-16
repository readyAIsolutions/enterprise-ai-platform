#!/usr/bin/env python3
"""MCP Knowledge Base Server - Exposes ENI skills/memories as resources"""
import json, os
from pathlib import Path

SKILLS_DIR = Path("/home/hunter/.hermes/skills")
MEMORIES_DIR = Path("/home/hunter/.hermes/memories")

def list_skills():
    skills = []
    for skill_dir in SKILLS_DIR.iterdir():
        if skill_dir.is_dir():
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                skills.append({"name": skill_dir.name, "path": str(skill_md)})
    return skills

def read_memory(category: str):
    mem_file = MEMORIES_DIR / f"{category}.md"
    return mem_file.read_text() if mem_file.exists() else ""

if __name__ == "__main__":
    print(json.dumps({"skills": list_skills(), "memories": ["user", "memory"]}))
