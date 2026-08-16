#!/usr/bin/env python3
"""
ENI Skill Forge Swarm Workers
Pattern extraction → Skill synthesis → Glyph assignment → Compression → Registration
"""

import asyncio
import json
import hashlib
import sqlite3
import time
import signal
import sys
import re
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import threading

KB_ROOT = Path("~/.eni/kb").expanduser()
SKILLS_DIR = KB_ROOT / "skills"
PATTERNS_DIR = KB_ROOT / "patterns_raw"
GLYPHS_DIR = KB_ROOT / "glyphs"
DICTS_DIR = KB_ROOT / "dicts"
DB_PATH = KB_ROOT / "skills.db"

for d in [SKILLS_DIR, PATTERNS_DIR, GLYPHS_DIR, DICTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))  # project lib/
sys.path.insert(0, str(KB_ROOT / "compression"))
sys.path.insert(0, str(KB_ROOT / "glyphs"))

from kb.legacy.compression_pipeline import ENICompressionPipeline
from kb.legacy.glyph_allocator import GlyphAllocator, DSLParser, DSLSpec, DSLParam, GlyphMap


@dataclass
class Pattern:
    name: str
    verb: str
    noun: str
    category: str
    description: str
    params: List[Dict] = field(default_factory=list)
    required: List[str] = field(default_factory=list)
    example: str = ""
    execution_mode: str = "subprocess"
    entrypoint: Optional[str] = None
    python_handler: Optional[str] = None
    http_endpoint: Optional[str] = None
    source_files: List[str] = field(default_factory=list)
    success_count: int = 0
    failure_count: int = 0
    signature: str = ""

    def __post_init__(self):
        if not self.signature:
            self.signature = hashlib.md5(f"{self.verb}:{self.noun}:{self.category}".encode()).hexdigest()[:12]


@dataclass
class ForgedSkill:
    skill_id: str
    glyph: str
    verb: str
    noun: str
    description: str
    dsl_spec: Dict[str, Any]
    mcp_schema: Dict[str, Any]
    lsp_capability: Dict[str, Any]
    execution_mode: str
    entrypoint: Optional[str]
    python_handler: Optional[str]
    http_endpoint: Optional[str]
    wenyan_hash: str
    rtk_hash: str
    pxpipe_png: bytes
    created_at: int
    updated_at: int
    pattern_signature: str
    usage_count: int = 0
    fitness: float = 0.0


class PatternExtractor:
    """Extract reusable patterns from completed tasks, code, logs."""

    def __init__(self, patterns_dir: Path, db: sqlite3.Connection):
        self.patterns_dir = patterns_dir
        self.db = db
        self._init_db()

    def _init_db(self):
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS patterns (
                signature TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                verb TEXT NOT NULL,
                noun TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                params TEXT NOT NULL,
                required TEXT NOT NULL,
                example TEXT,
                execution_mode TEXT NOT NULL,
                entrypoint TEXT,
                python_handler TEXT,
                http_endpoint TEXT,
                source_files TEXT NOT NULL,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                created_at INTEGER DEFAULT (strftime('%s','now')),
                updated_at INTEGER DEFAULT (strftime('%s','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_patterns_verb_noun ON patterns(verb, noun);
            CREATE INDEX IF NOT EXISTS idx_patterns_category ON patterns(category);
        """)
        self.db.commit()

    def extract_from_session(self, session_data: Dict) -> List[Pattern]:
        """Extract patterns from a completed session."""
        patterns = []

        # Look for tool calls that succeeded
        tools_used = session_data.get("tools_used", [])
        tool_sequences = self._find_repeated_sequences(tools_used)

        for seq in tool_sequences:
            pattern = self._sequence_to_pattern(seq)
            if pattern:
                patterns.append(pattern)

        # Look for file operations that form a workflow
        file_ops = session_data.get("file_operations", [])
        workflow_patterns = self._extract_file_workflows(file_ops)
        patterns.extend(workflow_patterns)

        # Look for command patterns
        commands = session_data.get("commands_run", [])
        cmd_patterns = self._extract_command_patterns(commands)
        patterns.extend(cmd_patterns)

        return patterns

    def _find_repeated_sequences(self, tools: List[Dict], min_len: int = 2, min_count: int = 2) -> List[List[Dict]]:
        """Find repeated tool call sequences."""
        sequences = []
        for i in range(len(tools) - min_len + 1):
            seq = tools[i:i + min_len]
            # Count occurrences
            count = 0
            for j in range(len(tools) - min_len + 1):
                if tools[j:j + min_len] == seq:
                    count += 1
            if count >= min_count:
                sequences.append(seq)
        return sequences

    def _sequence_to_pattern(self, seq: List[Dict]) -> Optional[Pattern]:
        """Convert tool sequence to pattern."""
        if not seq:
            return None

        # Infer verb/n
        first = seq[0]
        tool_name = first.get("tool", "")
        params = first.get("params", {})

        # Map common tools to verbs
        verb_map = {
            "terminal": "run",
            "write_file": "write",
            "read_file": "read",
            "patch": "edit",
            "search_files": "search",
            "patch": "modify",
            "execute_code": "compute",
        }
        verb = verb_map.get(tool_name, tool_name.replace("_", "-"))

        # Infer noun from params
        noun = params.get("path", params.get("command", params.get("pattern", "task"))).split("/")[-1]
        noun = re.sub(r'[^a-zA-Z0-9_-]', '_', noun)[:30]

        return Pattern(
            name=f"{verb}_{noun}",
            verb=verb,
            noun=noun,
            category="core",
            description=f"Auto-extracted from {tool_name} sequence",
            params=[{"name": k, "type": "string", "required": False} for k in params.keys()],
            required=list(params.keys())[:2],
            example=f"󰀀 {verb}:{noun}",
            source_files=[str(p) for p in params.values() if isinstance(p, str) and p.startswith("/")]
        )

    def _extract_file_workflows(self, ops: List[Dict]) -> List[Pattern]:
        """Extract patterns from file operations."""
        patterns = []
        # Group by directory
        by_dir = {}
        for op in ops:
            path = op.get("path", "")
            if path:
                dir_path = str(Path(path).parent)
                by_dir.setdefault(dir_path, []).append(op)

        for dir_path, dir_ops in by_dir.items():
            if len(dir_ops) >= 3:  # At least 3 ops in same dir
                verbs = [op.get("operation", "") for op in dir_ops]
                pattern = Pattern(
                    name=f"workflow_{Path(dir_path).name}",
                    verb="workflow",
                    noun=Path(dir_path).name,
                    category="core",
                    description=f"File workflow in {dir_path}",
                    params=[{"name": "path", "type": "path", "required": True, "default": dir_path}],
                    required=["path"],
                    example=f"󰀀 workflow:{Path(dir_path).name} @path={dir_path}",
                    source_files=[op.get("path", "") for op in dir_ops]
                )
                patterns.append(pattern)
        return patterns

    def _extract_command_patterns(self, commands: List[str]) -> List[Pattern]:
        """Extract patterns from shell commands."""
        patterns = []
        cmd_groups = {}

        for cmd in commands:
            # Parse command
            parts = cmd.split()
            if not parts:
                continue
            base_cmd = parts[0]
            args = parts[1:]

            # Group by base command
            if base_cmd not in cmd_groups:
                cmd_groups[base_cmd] = []
            cmd_groups[base_cmd].append({"args": args, "full": cmd})

        for base_cmd, instances in cmd_groups.items():
            if len(instances) >= 2:  # Repeated command
                # Find common arg patterns
                common_args = self._find_common_args([i["args"] for i in instances])
                pattern = Pattern(
                    name=f"cmd_{base_cmd.replace('/', '_')}",
                    verb="cmd",
                    noun=base_cmd.replace('/', '_').replace('.', '_'),
                    category="core",
                    description=f"Repeated command: {base_cmd}",
                    params=[{"name": f"arg{i}", "type": "string", "required": False} for i in range(len(common_args))],
                    required=[],
                    example=f"󰀀 cmd:{base_cmd.replace('/', '_')}",
                    execution_mode="subprocess",
                    entrypoint=base_cmd,
                    source_files=[i["full"] for i in instances[:3]]
                )
                patterns.append(pattern)
        return patterns

    def _find_common_args(self, arg_lists: List[List[str]]) -> List[str]:
        """Find common argument patterns."""
        if not arg_lists:
            return []
        # Simple: return args from first instance
        return arg_lists[0]

    def extract_from_files(self, file_paths: List[Path]) -> List[Pattern]:
        """Extract patterns from source files (scripts, configs, etc.)."""
        patterns = []
        for fpath in file_paths:
            if not fpath.exists():
                continue
            try:
                content = fpath.read_text()
                # Look for function definitions, CLI commands, etc.
                funcs = re.findall(r'^(def|function|func)\s+(\w+)', content, re.MULTILINE)
                for _, fname in funcs:
                    if not fname.startswith('_'):
                        pattern = Pattern(
                            name=f"func_{fname}",
                            verb="call",
                            noun=fname,
                            category="core",
                            description=f"Function {fname} from {fpath.name}",
                            params=[{"name": "args", "type": "string", "required": False}],
                            required=[],
                            example=f"󰀀 call:{fname}",
                            execution_mode="python",
                            python_handler=f"{fpath.stem}.{fname}",
                            source_files=[str(fpath)]
                        )
                        patterns.append(pattern)
            except Exception:
                pass
        return patterns

    def save_patterns(self, patterns: List[Pattern]) -> List[Pattern]:
        """Save new patterns, return only newly added ones."""
        new_patterns = []
        for p in patterns:
            cur = self.db.execute("SELECT signature FROM patterns WHERE signature=?", (p.signature,))
            if not cur.fetchone():
                self.db.execute("""
                    INSERT INTO patterns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    p.signature, p.name, p.verb, p.noun, p.category, p.description,
                    json.dumps(p.params), json.dumps(p.required), p.example,
                    p.execution_mode, p.entrypoint, p.python_handler, p.http_endpoint,
                    json.dumps(p.source_files), p.success_count, p.failure_count
                ))
                new_patterns.append(p)
        self.db.commit()
        return new_patterns

    def get_unforged_patterns(self, min_success: int = 2) -> List[Pattern]:
        """Get patterns that haven't been forged into skills yet."""
        cur = self.db.execute("""
            SELECT * FROM patterns
            WHERE success_count >= ? AND signature NOT IN (
                SELECT pattern_signature FROM skills WHERE pattern_signature IS NOT NULL
            )
            ORDER BY success_count DESC, updated_at DESC
        """, (min_success,))

        patterns = []
        for row in cur.fetchall():
            p = Pattern(
                signature=row[0], name=row[1], verb=row[2], noun=row[3],
                category=row[4], description=row[5],
                params=json.loads(row[6]), required=json.loads(row[7]),
                example=row[8], execution_mode=row[9], entrypoint=row[10],
                python_handler=row[11], http_endpoint=row[12],
                source_files=json.loads(row[13]),
                success_count=row[14], failure_count=row[15]
            )
            patterns.append(p)
        return patterns


class SkillForge:
    """Forge skills from patterns."""

    def __init__(self, kb_root: Path):
        self.kb_root = kb_root
        self.compression = ENICompressionPipeline()
        self.allocator = GlyphAllocator()
        self.parser = DSLParser(self.allocator)
        self.glyph_map = GlyphMap(self.allocator, self.parser)
        self.db = sqlite3.connect(DB_PATH)
        self._init_skills_db()

    def _init_skills_db(self):
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
                updated_at INTEGER DEFAULT (strftime('%s','now')),
                pattern_signature TEXT,
                usage_count INTEGER DEFAULT 0,
                fitness REAL DEFAULT 0.0
            );
            CREATE INDEX IF NOT EXISTS idx_skills_verb_noun ON skills(verb, noun);
            CREATE INDEX IF NOT EXISTS idx_skills_glyph ON skills(glyph);
            CREATE INDEX IF NOT EXISTS idx_skills_pattern ON skills(pattern_signature);
        """)
        self.db.commit()

    def forge_skill(self, pattern: Pattern) -> Optional[ForgedSkill]:
        """Forge a single skill from a pattern."""
        # Check if already exists
        cur = self.db.execute("SELECT skill_id FROM skills WHERE pattern_signature=?", (pattern.signature,))
        if cur.fetchone():
            return None

        # Generate skill ID
        skill_id = f"eni:{pattern.verb}:{pattern.noun}"

        # Check for collision
        cur = self.db.execute("SELECT 1 FROM skills WHERE skill_id=?", (skill_id,))
        if cur.fetchone():
            # Add hash suffix
            skill_id = f"{skill_id}_{pattern.signature[:6]}"

        # Allocate glyph
        glyph = self.allocator.allocate(pattern.category, skill_id)

        # Build DSL spec
        dsl_params = []
        for p in pattern.params:
            dsl_params.append(DSLParam(
                name=p.get("name", "arg"),
                type=p.get("type", "string"),
                required=p.get("required", False),
                default=p.get("default"),
                enum=p.get("enum", []),
                description=p.get("description", "")
            ))

        dsl_spec = DSLSpec(
            verb=f"{pattern.verb}:{pattern.noun}",
            params=dsl_params,
            examples=[pattern.example] if pattern.example else [f"{glyph} {pattern.verb}:{pattern.noun}"],
            description=pattern.description
        )

        # Generate MCP schema
        mcp_schema = self._generate_mcp_schema(dsl_spec, skill_id)

        # Generate LSP capability
        lsp_cap = self._generate_lsp_capability(dsl_spec, skill_id)

        # Compress skill
        skill_data = {
            "skill_id": skill_id,
            "glyph": glyph,
            "verb": pattern.verb,
            "noun": pattern.noun,
            "description": pattern.description,
            "dsl_spec": asdict(dsl_spec),
            "mcp_schema": mcp_schema,
            "lsp_capability": lsp_cap,
            "execution_mode": pattern.execution_mode,
            "entrypoint": pattern.entrypoint,
            "python_handler": pattern.python_handler,
            "http_endpoint": pattern.http_endpoint
        }

        compression_result = self.compression.compress(json.dumps(skill_data))
        wenyan_hash = compression_result["dict_hashes"]["wenyan"]
        rtk_hash = compression_result["dict_hashes"]["rtk"]

        # Read PNG carrier
        pxpipe_png = b""
        if compression_result.get("carrier_path"):
            pxpipe_png = Path(compression_result["carrier_path"]).read_bytes()

        # Create forged skill
        forged = ForgedSkill(
            skill_id=skill_id,
            glyph=glyph,
            verb=pattern.verb,
            noun=pattern.noun,
            description=pattern.description,
            dsl_spec=asdict(dsl_spec),
            mcp_schema=mcp_schema,
            lsp_capability=lsp_cap,
            execution_mode=pattern.execution_mode,
            entrypoint=pattern.entrypoint,
            python_handler=pattern.python_handler,
            http_endpoint=pattern.http_endpoint,
            wenyan_hash=wenyan_hash,
            rtk_hash=rtk_hash,
            pxpipe_png=pxpipe_png,
            created_at=int(time.time()),
            updated_at=int(time.time()),
            pattern_signature=pattern.signature
        )

        return forged

    def _generate_mcp_schema(self, dsl_spec: DSLSpec, skill_id: str) -> Dict:
        """Generate MCP tool schema from DSL spec."""
        properties = {}
        required = []

        for param in dsl_spec.params:
            prop = {"type": param.type}
            if param.enum:
                prop["enum"] = param.enum
            if param.description:
                prop["description"] = param.description
            if param.default is not None:
                prop["default"] = param.default
            properties[param.name] = prop
            if param.required:
                required.append(param.name)

        return {
            "name": skill_id,
            "description": dsl_spec.description,
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }

    def _generate_lsp_capability(self, dsl_spec: DSLSpec, skill_id: str) -> Dict:
        """Generate LSP capability from DSL spec."""
        return {
            "skill_id": skill_id,
            "completionTrigger": dsl_spec.verb.split(":")[0] if ":" in dsl_spec.verb else dsl_spec.verb,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "required": p.required,
                    "description": p.description,
                    "enum": p.enum
                }
                for p in dsl_spec.params
            ],
            "documentation": dsl_spec.description,
            "examples": dsl_spec.examples
        }

    def register_skill(self, forged: ForgedSkill):
        """Register forged skill in DB and update allocator."""
        # Insert into skills DB
        self.db.execute("""
            INSERT INTO skills VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            forged.skill_id, forged.glyph, forged.verb, forged.noun,
            forged.description, json.dumps(forged.dsl_spec),
            json.dumps(forged.mcp_schema), json.dumps(forged.lsp_capability),
            forged.execution_mode, forged.entrypoint, forged.python_handler,
            forged.http_endpoint, forged.wenyan_hash, forged.rtk_hash,
            forged.pxpipe_png, forged.created_at, forged.updated_at,
            forged.pattern_signature, forged.usage_count, forged.fitness
        ))
        self.db.commit()

        # Register with allocator
        dsl_spec = DSLSpec(**forged.dsl_spec)
        self.allocator.register_skill(forged.glyph, forged.skill_id, dsl_spec)

        # Write skill file
        skill_file = SKILLS_DIR / f"{forged.skill_id.replace(':', '_')}.json"
        skill_file.write_text(json.dumps(asdict(forged), indent=2))

        # Write carrier PNG
        if forged.pxpipe_png:
            carrier_file = KB_ROOT / "carriers" / f"{forged.glyph}_{forged.skill_id.replace(':', '_')}.png"
            carrier_file.write_bytes(forged.pxpipe_png)

        print(f"[FORGED] {forged.glyph} {forged.verb}:{forged.noun} ({forged.skill_id})")


class SkillForgeWorker:
    """Swarm worker that continuously forges skills from patterns."""

    def __init__(self, kb_root: Path, worker_id: int, total_workers: int):
        self.kb_root = kb_root
        self.worker_id = worker_id
        self.total_workers = total_workers
        self.db = sqlite3.connect(DB_PATH)
        self.extractor = PatternExtractor(PATTERNS_DIR, self.db)
        self.forge = SkillForge(kb_root)
        self.running = True
        self.forged_count = 0

        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)

    def _shutdown(self, *args):
        self.running = False

    async def run_forever(self, interval: int = 30):
        print(f"[WORKER {self.worker_id}/{self.total_workers}] Starting forge loop, interval={interval}s")
        while self.running:
            try:
                await self._forge_cycle()
            except Exception as e:
                print(f"[WORKER {self.worker_id}] ERROR: {e}", file=sys.stderr)
            await asyncio.sleep(interval)

    async def _forge_cycle(self):
        # Get unforged patterns
        patterns = self.extractor.get_unforged_patterns(min_success=2)

        # Distribute among workers (simple round-robin by signature hash)
        my_patterns = []
        for p in patterns:
            sig_hash = int(p.signature, 16)
            if sig_hash % self.total_workers == self.worker_id:
                my_patterns.append(p)

        for pattern in my_patterns:
            try:
                forged = self.forge.forge_skill(pattern)
                if forged:
                    self.forge.register_skill(forged)
                    self.forged_count += 1
            except Exception as e:
                print(f"[WORKER {self.worker_id}] Forge error for {pattern.name}: {e}", file=sys.stderr)


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb-root", type=Path, default=KB_ROOT)
    parser.add_argument("--worker-id", type=int, default=0)
    parser.add_argument("--total-workers", type=int, default=9)
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--single-cycle", action="store_true")
    args = parser.parse_args()

    worker = SkillForgeWorker(args.kb_root, args.worker_id, args.total_workers)

    if args.single_cycle:
        await worker._forge_cycle()
        print(f"Forged {worker.forged_count} skills")
    else:
        await worker.run_forever(args.interval)


if __name__ == "__main__":
    asyncio.run(main())