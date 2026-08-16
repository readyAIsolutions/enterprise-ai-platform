#!/usr/bin/env python3
# swarm_worker.py — ENI KB Skill Forge Worker
# Runs as infinite daemon, forges skills from observed patterns

import asyncio, json, hashlib, sqlite3, time, signal, sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional
import zlib, base64

from eni_kb.compression.pipeline import wenyan_compress, rtk_compress, compress_skill
from eni_kb.glyphs.allocator import allocate_glyph, register_skill
from eni_kb.mcp.schema import skill_to_mcp_tool
from eni_kb.lsp.capabilities import skill_to_lsp_capability
from eni_kb.patterns.extractor import extract_patterns
from eni_kb.pxpipe.codec import encode_png, decode_png

@dataclass
class SkillPackage:
    skill_id: str
    glyph: str
    verb: str
    noun: str
    description: str
    dsl_spec: dict
    mcp_schema: dict
    lsp_capability: dict
    execution_mode: str  # subprocess | python | http
    entrypoint: Optional[str] = None
    python_handler: Optional[str] = None
    http_endpoint: Optional[str] = None
    wenyan_hash: str = ""
    rtk_hash: str = ""
    pxpipe_png: bytes = b""
    created_at: int = 0
    updated_at: int = 0

class SkillForgeWorker:
    def __init__(self, kb_root: Path, workers: int = 9):
        self.kb_root = Path(kb_root)
        self.workers = workers
        self.db = sqlite3.connect(self.kb_root / "skills.db")
        self._init_db()
        self.running = True
        self.patterns_dir = self.kb_root / "patterns_raw"
        self.skills_dir = self.kb_root / "skills"
        self.glyphs_dir = self.kb_root / "glyphs"
        self.dicts_dir = self.kb_root / "dicts"
        
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)
    
    def _init_db(self):
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS skills (
                skill_id TEXT PRIMARY KEY,
                glyph TEXT NOT NULL UNIQUE,
                verb TEXT NOT NULL,
                noun TEXT NOT NULL,
                description TEXT,
                dsl_spec TEXT NOT NULL,
                mcp_schema TEXT NOT NULL,
                lsp_capability TEXT NOT NULL,
                execution_mode TEXT NOT NULL,
                entrypoint TEXT,
                python_handler TEXT,
                http_endpoint TEXT,
                wenyan_hash TEXT NOT NULL,
                rtk_hash TEXT NOT NULL,
                pxpipe_png BLOB,
                created_at INTEGER DEFAULT (strftime('%s','now')),
                updated_at INTEGER DEFAULT (strftime('%s','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_skills_verb_noun ON skills(verb, noun);
            CREATE INDEX IF NOT EXISTS idx_skills_glyph ON skills(glyph);
        """)
        self.db.commit()
    
    def _shutdown(self, *args):
        self.running = False
    
    def forge_cycle(self) -> list[SkillPackage]:
        """One forge cycle: extract patterns → forge skills → register"""
        forged = []
        
        # 1. Extract new patterns from raw sources
        patterns = extract_patterns(self.patterns_dir, self.db)
        if not patterns:
            return forged
        
        # 2. Distribute patterns to workers (round-robin for simplicity)
        for i, pattern in enumerate(patterns):
            if i % self.workers != 0:  # Only worker 0 in this process
                continue
            
            try:
                skill = self._forge_skill(pattern)
                if skill:
                    forged.append(skill)
            except Exception as e:
                print(f"[FORGE ERROR] {pattern.get('name', 'unknown')}: {e}", file=sys.stderr)
        
        return forged
    
    def _forge_skill(self, pattern: dict) -> Optional[SkillPackage]:
        """Forge a single skill from a pattern"""
        # Generate skill ID
        verb = pattern.get("verb", "unknown")
        noun = pattern.get("noun", "task")
        skill_id = f"eni:{verb}:{noun}"
        
        # Check if already exists
        cur = self.db.execute("SELECT 1 FROM skills WHERE skill_id=?", (skill_id,))
        if cur.fetchone():
            return None  # Already forged
        
        # Allocate glyph
        category = pattern.get("category", "core")
        glyph = allocate_glyph(category)
        
        # Build DSL spec
        dsl_spec = {
            "verb": verb,
            "noun": noun,
            "params": pattern.get("params", []),
            "required": pattern.get("required", []),
            "example": pattern.get("example", f"{glyph} {verb}:{noun}")
        }
        
        # Build MCP schema
        mcp_schema = skill_to_mcp_tool(dsl_spec)
        
        # Build LSP capability
        lsp_cap = skill_to_lsp_capability(dsl_spec)
        
        # Compression hashes
        wenyan_hash = hashlib.sha256(
            open(self.dicts_dir / "wenyan_dict.msgpack", "rb").read()
        ).hexdigest()
        rtk_hash = hashlib.sha256(
            open(self.dicts_dir / "rtk_map.msgpack", "rb").read()
        ).hexdigest()
        
        # Create skill package
        skill = SkillPackage(
            skill_id=skill_id,
            glyph=glyph,
            verb=verb,
            noun=noun,
            description=pattern.get("description", ""),
            dsl_spec=dsl_spec,
            mcp_schema=mcp_schema,
            lsp_capability=lsp_cap,
            execution_mode=pattern.get("execution_mode", "subprocess"),
            entrypoint=pattern.get("entrypoint"),
            python_handler=pattern.get("python_handler"),
            http_endpoint=pattern.get("http_endpoint"),
            wenyan_hash=wenyan_hash[:16],
            rtk_hash=rtk_hash[:16],
            created_at=int(time.time()),
            updated_at=int(time.time())
        )
        
        # Compress and encode to PxPipe PNG
        skill.pxpipe_png = compress_skill(skill, self.dicts_dir)
        
        return skill
    
    def _register_skills(self, skills: list[SkillPackage]):
        """Register forged skills in DB and notify MCP/LSP"""
        for skill in skills:
            # Insert into DB
            self.db.execute("""
                INSERT INTO skills VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                skill.skill_id, skill.glyph, skill.verb, skill.noun,
                skill.description, json.dumps(skill.dsl_spec),
                json.dumps(skill.mcp_schema), json.dumps(skill.lsp_capability),
                skill.execution_mode, skill.entrypoint, skill.python_handler,
                skill.http_endpoint, skill.wenyan_hash, skill.rtk_hash,
                skill.pxpipe_png, skill.created_at, skill.updated_at
            ))
            
            # Register glyph allocation
            register_skill(skill.glyph, skill.skill_id)
            
            # Write individual skill file (for backup/inspection)
            skill_file = self.skills_dir / f"{skill.skill_id.replace(':', '_')}.json"
            skill_file.write_text(json.dumps(asdict(skill), indent=2))
            
            print(f"[FORGED] {skill.glyph} {skill.verb}:{skill.noun} ({skill.skill_id})")
        
        self.db.commit()
    
    async def run_forever(self, interval: int = 30):
        """Main loop"""
        print(f"[SWARM WORKER] Starting with {self.workers} workers, interval={interval}s")
        
        while self.running:
            try:
                forged = self.forge_cycle()
                if forged:
                    self._register_skills(forged)
                    # Notify MCP/LSP of new tools (via file watch or IPC)
                    self._notify_servers()
            except Exception as e:
                print(f"[SWARM ERROR] {e}", file=sys.stderr)
            
            await asyncio.sleep(interval)
    
    def _notify_servers(self):
        """Touch a file that MCP/LSP watch for tool list changes"""
        (self.kb_root / ".skills_changed").write_text(str(time.time()))


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb-root", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=9)
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--daemonize", action="store_true")
    args = parser.parse_args()
    
    worker = SkillForgeWorker(args.kb_root, args.workers)
    await worker.run_forever(args.interval)


if __name__ == "__main__":
    asyncio.run(main())