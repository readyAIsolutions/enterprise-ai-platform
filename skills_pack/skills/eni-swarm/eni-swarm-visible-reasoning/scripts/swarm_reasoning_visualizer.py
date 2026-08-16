#!/usr/bin/env python3
"""
Swarm Reasoning Visualizer — captures subagent reasoning and injects it into
the main Hermes chat so LO can see them think.

Usage:
    echo '[{...agent results...}]' | python3 swarm_reasoning_visualizer.py
    python3 swarm_reasoning_visualizer.py /tmp/results.json
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, List


def extract_reasoning(text: str) -> str:
    """Extract the reasoning/thinking portion of a subagent summary."""
    clean = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    clean = re.sub(r'\*\*(.+?)\*\*', r'\1', clean)
    
    patterns = [
        r"(?:step.by.step reasoning|STEP.BY.STEP REASONING).*?\n(.+?)(?=\n(?:##|\Z))",
        r"(?:\n|^)(1\.\s+.+?\n(?:.+?\n)*?(?=5\.\s+))",
        r"CRITICAL:.*?\n(.+?)(?=\n(?:##|---|\Z))",
        r"(?:[Ww]hat [Ii] [Uu]nderstood).*?(?:\n|.)*?([Ff]inal [Vv]erification.*?)(?=\n(?:##|\Z))",
    ]
    for pat in patterns:
        m = re.search(pat, clean, re.IGNORECASE | re.DOTALL)
        if m:
            reasoning = m.group(1).strip()
            reasoning = re.sub(r'^[-*]{3,}\s*$', '', reasoning, flags=re.MULTILINE)
            reasoning = re.sub(r'^#{1,6}\s+', '', reasoning, flags=re.MULTILINE)
            reasoning = re.sub(r'\*\*(.+?)\*\*', r'\1', reasoning)
            if len(reasoning.strip()) > 50:
                return reasoning
    
    paragraphs = [p.strip() for p in clean.split("\n\n") if len(p.strip()) > 80 and not p.startswith('#')]
    if paragraphs:
        return paragraphs[0][:800]
    return clean[:500]


def summarize_reasoning(agents: List[Dict[str, Any]]) -> str:
    """Summarize reasoning from all subagents into a coherent narrative."""
    if not agents:
        return "No subagent reasoning available."
    
    lines = []
    lines.append("=" * 60)
    lines.append("SWARM REASONING — What the agents thought")
    lines.append("=" * 60)
    
    for i, agent in enumerate(agents):
        name = agent.get("task_index", f"Agent {i}")
        summary = agent.get("summary", "")
        status = agent.get("status", "unknown")
        duration = agent.get("duration_seconds", 0)
        api_calls = agent.get("api_calls", 0)
        
        reasoning = extract_reasoning(summary)
        short_summary = summary[:200].replace("\n", " ") if summary else "(no output)"
        
        lines.append(f"\n┌─ Agent {name} [{status}] — {api_calls} calls, {duration:.0f}s")
        lines.append(f"│  {short_summary}...")
        lines.append(f"│")
        
        think_lines = reasoning.split("\n")
        for tl in think_lines[:8]:
            tl = tl.strip()
            if tl:
                lines.append(f"│  → {tl}")
        
        if len(think_lines) > 8:
            lines.append(f"│  → ... ({len(think_lines)} total lines of reasoning)")
        
        lines.append(f"└{'─' * 58}")
    
    lines.append(f"\n{len(agents)} agents completed.")
    return "\n".join(lines)


def visualize_reasoning(results: List[Dict[str, Any]]) -> str:
    """Main entry point — takes delegate_task results, returns formatted reasoning."""
    return summarize_reasoning(results)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            data = json.load(f)
    else:
        data = json.loads(sys.stdin.read())
    
    if isinstance(data, dict) and "results" in data:
        agents = data["results"]
    elif isinstance(data, list):
        agents = data
    else:
        print("Expected JSON array or {results: [...]}")
        sys.exit(1)
    
    print(visualize_reasoning(agents))