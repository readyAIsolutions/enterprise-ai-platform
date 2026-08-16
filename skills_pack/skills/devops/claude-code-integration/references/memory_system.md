# Memory System Integration (Based on claudemd.ts)

This documents the full CLAUDE.md memory system ported from Claude Code to Hermes.

## Memory Tier Hierarchy

```python
MEMORY_TIERS = [
    # 1. Managed (global, read-only, highest priority)
    ('managed', '/etc/hermes-agent/CLAUDE.md'),
    
    # 2. User (personal global, git-ignored)
    ('user', '~/.hermes/CLAUDE.md'),
    
    # 3. Project (git-tracked, team-shared)
    ('project', 'CLAUDE.md'),
    ('project', '.claude/CLAUDE.md'),
    ('project', '.claude/rules/*.md'),  # All .md in rules dir
    
    # 4. Local (private, git-ignored, highest priority)
    ('local', 'CLAUDE.local.md'),
]

# Loading order: Managed → User → Project (closest first) → Local
# Priority: Last loaded = highest priority (overwrites earlier)
```

## @include Directive Support

```python
# Syntax: @path, @./relative, @~/home, @/absolute
# Works in leaf text nodes only (not code blocks)

INCLUDE_PATTERNS = [
    r'@(?:\./|~/|/)?[^\s\\]+'  # @ followed by valid path
]

# Fragment identifiers stripped: @file.md#section → @file.md
# Escaped spaces: @path\ with\ spaces → @path with spaces
```

## Frontmatter Path Globs

```yaml
# CLAUDE.md frontmatter:
---
paths:
  - "src/**"
  - "tests/**"
  - "*.py"
---

# Applies this file only to matching paths
# ** matches recursively (like glob)
```

## HTML Comment Stripping

```python
# Strip block-level HTML comments only:
# <!-- this gets stripped -->
# <!-- 
#   multi-line
#   comment
# -->
# But preserves: `inline <!-- comment --> code`
```

## AutoMem Entry Points

```python
# AutoMem: Generated memory from codebase analysis
# TeamMem: Shared team memory (feature flag)
# Both truncated to line AND byte caps:

MAX_MEMORY_CHARACTERS = 40000
MAX_LINES = 500

def truncate_entrypoint(content: str) -> TruncatedResult:
    lines = content.split('\n')
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES]
        content = '\n'.join(lines)
    
    if len(content) > MAX_MEMORY_CHARACTERS:
        content = content[:MAX_MEMORY_CHARACTERS] + '\n... [truncated]'
    
    return TruncatedResult(content=content, truncated=truncated)
```

## Text File Extensions Whitelist

```python
TEXT_EXTENSIONS = {
    # Markdown/Text
    '.md', '.txt', '.text',
    # Data
    '.json', '.yaml', '.yml', '.toml', '.xml', '.csv',
    # Web
    '.html', '.htm', '.css', '.scss', '.sass', '.less',
    # JS/TS
    '.js', '.ts', '.tsx', '.jsx', '.mjs', '.cjs', '.mts', '.cts',
    # Python
    '.py', '.pyi', '.pyw',
    # Ruby
    '.rb', '.erb', '.rake',
    # Go
    '.go',
    # Rust
    '.rs',
    # Java/Kotlin/Scala
    '.java', '.kt', '.kts', '.scala',
    # C/C++
    '.c', '.cpp', '.cc', '.cxx', '.h', '.hpp', '.hxx',
    # C#
    '.cs',
    # Swift
    '.swift',
    # Shell
    '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd',
    # Config
    '.env', '.ini', '.cfg', '.conf', '.config', '.properties',
    # Database
    '.sql', '.graphql', '.gql',
    # Protocol
    '.proto',
    # Frontend
    '.vue', '.svelte', '.astro',
    # Template
    '.ejs', '.hbs', '.pug', '.jade',
    # Other
    '.php', '.pl', '.pm', '.lua', '.r', '.R', '.dart',
    '.hs', '.lhs', '.elm', '.ml', '.mli', '.f', '.f90', '.f95', '.for',
    # Build
    '.cmake', '.make', '.makefile', '.gradle', '.sbt',
    # Docs
    '.rst', '.adoc', '.asciidoc', '.org', '.tex', '.latex',
    # Lock files
    '.lock',
    # Misc
    '.log', '.diff', '.patch',
}
```

## Implementation: MemoryLoader

```python
import os
import glob
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
from marked import Lexer  # or python-markdown

@dataclass
class MemoryFile:
    path: str
    type: str  # 'managed' | 'user' | 'project' | 'local' | 'AutoMem' | 'TeamMem'
    content: str
    globs: Optional[List[str]] = None
    parent: Optional[str] = None  # @include parent
    content_differs_from_disk: bool = False
    raw_content: Optional[str] = None

class MemoryLoader:
    def __init__(self, original_cwd: str):
        self.original_cwd = Path(original_cwd).resolve()
        self.processed = set()  # For circular @include detection
    
    def load_all(self) -> List[MemoryFile]:
        memories = []
        
        # 1. Managed
        memories.extend(self._load_tier('managed', self._get_managed_paths()))
        
        # 2. User
        memories.extend(self._load_tier('user', self._get_user_paths()))
        
        # 3. Project (closest to cwd first)
        memories.extend(self._load_tier('project', self._get_project_paths()))
        
        # 4. Local
        memories.extend(self._load_tier('local', self._get_local_paths()))
        
        # 5. AutoMem/TeamMem (if enabled)
        if is_auto_memory_enabled():
            memories.extend(self._load_automem())
        
        return memories
    
    def _load_tier(self, tier: str, paths: List[Path]) -> List[MemoryFile]:
        results = []
        for path in paths:
            if not path.exists():
                continue
            if path.is_dir():
                for sub in path.glob('*.md'):
                    results.extend(self._process_file(sub, tier))
            else:
                results.extend(self._process_file(path, tier))
        return results
    
    def _process_file(self, path: Path, tier: str) -> List[MemoryFile]:
        # Check extension
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            return []
        
        try:
            raw = path.read_text(encoding='utf-8')
        except Exception as e:
            if isinstance(e, (FileNotFoundError, IsADirectoryError)):
                return []
            if isinstance(e, PermissionError):
                log_permission_error(path)
                return []
            raise
        
        # Parse frontmatter
        frontmatter, content = parse_frontmatter(raw)
        globs = parse_frontmatter_paths(frontmatter.get('paths')) if frontmatter.get('paths') else None
        
        # Lex once for comment stripping and @include extraction
        has_comment = '<!--' in content
        needs_lex = has_comment or include_base is not None
        tokens = Lexer(gfm=False).lex(content) if needs_lex else None
        
        # Strip HTML comments
        if has_comment and tokens:
            content = strip_html_comments(tokens)
        
        # Extract @include paths
        include_paths = []
        if tokens and include_base:
            include_paths = extract_includes(tokens, include_base)
        
        # Truncate AutoMem/TeamMem
        if tier in ('AutoMem', 'TeamMem'):
            content = truncate_entrypoint(content).content
        
        # Track if content differs from disk (frontmatter strip, comment strip, truncate)
        differs = content != raw
        
        return [MemoryFile(
            path=str(path),
            type=tier,
            content=content,
            globs=globs,
            content_differs_from_disk=differs,
            raw_content=raw if differs else None
        )]
    
    def _extract_includes(self, tokens, base_path: str) -> List[str]:
        """Extract @includes from markdown tokens."""
        paths = set()
        
        def extract_from_text(text: str):
            for match in INCLUDE_REGEX.finditer(text):
                path = match.group(1)
                if not path:
                    continue
                # Strip fragments
                if '#' in path:
                    path = path.split('#')[0]
                if not path:
                    continue
                # Unescape spaces
                path = path.replace('\\ ', ' ')
                # Validate
                if self._is_valid_include_path(path):
                    resolved = expand_path(path, os.path.dirname(base_path))
                    paths.add(resolved)
        
        def process_tokens(token_list):
            for token in token_list:
                if token['type'] in ('code', 'codespan'):
                    continue
                if token['type'] == 'html':
                    # Strip comments from html tokens too
                    text = token['raw']
                    if text.strip().startswith('<!--') and '-->' in text:
                        text = text.replace(re_comment, '')
                    extract_from_text(text)
                elif token.get('text'):
                    extract_from_text(token['text'])
                for key in ('tokens', 'items'):
                    if token.get(key):
                        process_tokens(token[key])
        
        process_tokens(tokens)
        return list(paths)
    
    def _is_valid_include_path(self, path: str) -> bool:
        return (
            path.startswith('./') or
            path.startswith('~/') or
            (path.startswith('/') and path != '/') or
            (not path.startswith('@') and 
             not re.match(r'^[#%^&*()]+$', path) and
             re.match(r'^[a-zA-Z0-9._-]', path))
        )


# Memory Prompt Construction
def build_memory_prompt(memories: List[MemoryFile]) -> str:
    """Build the instruction prompt with all memories."""
    if not memories:
        return ""
    
    parts = [
        "Codebase and user instructions are shown below. "
        "IMPORTANT: These instructions OVERRIDE any default behavior "
        "and you MUST follow them exactly as written."
    ]
    
    for mem in memories:
        header = f"\n## {mem.type.upper()} MEMORY: {mem.path}\n"
        if mem.globs:
            header += f"[Applies to: {', '.join(mem.globs)}]\n"
        parts.append(header + mem.content)
    
    return '\n'.join(parts)


# Instructions Loaded Hook
async def execute_instructions_loaded_hooks(
    memories: List[MemoryFile],
    reason: str  # 'session_start' | 'file_change' | 'config_change' | 'manual'
):
    """Execute InstructionsLoaded hooks after memory reload."""
    from hooks import execute_hook
    
    for mem in memories:
        await execute_hook('InstructionsLoaded', {
            'memory_type': mem.type,
            'memory_path': mem.path,
            'reason': reason,
            'content': mem.content
        })
```

## Integration with Hermes Config

```yaml
# config.yaml
memory:
  enabled: true
  auto_memory: true          # Enable AutoMem
  team_memory: false         # TeamMem (feature flag)
  managed_path: /etc/hermes-agent/CLAUDE.md
  user_path: ~/.hermes/CLAUDE.md
  project_patterns:
    - CLAUDE.md
    - .claude/CLAUDE.md
    - .claude/rules/*.md
  local_name: CLAUDE.local.md
  max_characters: 40000
  max_lines: 500
  
hooks:
  InstructionsLoaded:
    - matcher: "*"
      hooks:
        - command: "echo 'Memory loaded: $MEMORY_TYPE $MEMORY_PATH'"
```

## Usage in Agent

```python
class Agent:
    def __init__(self):
        self.memory_loader = MemoryLoader(os.getcwd())
        self.memories = []
    
    async def start_session(self):
        self.memories = self.memory_loader.load_all()
        system_prompt = build_memory_prompt(self.memories)
        
        # Execute hooks
        await execute_instructions_loaded_hooks(
            self.memories, 'session_start'
        )
        
        return system_prompt
    
    async def on_file_change(self, path: str):
        # Reload if path matches any memory glob
        for mem in self.memories:
            if mem.globs and any(fnmatch.fnmatch(path, g) for g in mem.globs):
                self.memories = self.memory_loader.load_all()
                await execute_instructions_loaded_hooks(
                    self.memories, 'file_change'
                )
                break
```