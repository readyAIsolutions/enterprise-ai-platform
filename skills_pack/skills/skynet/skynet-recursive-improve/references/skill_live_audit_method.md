# Skill Live-Audit Method

How to quality-audit Hermes skills against the live system (not just read the files).

## Audit dimensions

For each skill under audit, check these 5 axes against the live system:

### 1. Path existence
- Every absolute path referenced in the skill body → `test -e` or `ls -d`
- Every `references/`, `templates/`, `scripts/` linked file → verify on disk
- SKILL.md claims vs skill_view(linked_files=) output → cross-check

### 2. Package / command availability
- Every `import X` in code blocks → `python3 -c "import X"`
- Every CLI referenced → `which <cmd>` or `command -v <cmd>`
- Version-sensitive claims (e.g. "wine32 not installed by default") → `dpkg -l | grep wine32`

### 3. Windows-path detection
- Regex: `(?<![A-Za-z])[A-Z]:[\\/][\\/A-Za-z0-9_ .-]+` (uppercase drive letter + negative lookbehind to skip `https://`)
- Check if Windows paths are GATED (pre-flight check blocks execution) or RAW (will fail when copy-pasted)
- A gated path is acceptable; an un-gated one is a bug

### 4. Service liveness
- Ports claimed as listening → `ss -tlnp | grep <port>`
- Servers claimed as running → `pgrep -f <server>`
- Model caches claimed as present → `ls -d ~/.cache/huggingface/hub/models--*/`

### 5. Redundancy detection
- Same domain covered by 2+ skills → compare line counts, shared references (md5sum), trigger conditions
- Flag pairs where one skill is clearly the more complete/battle-tested version

## Verification command template

```bash
# Batch path check
for f in path1 path2 path3; do test -e "$f" && echo "EXISTS: $f" || echo "MISSING: $f"; done

# Batch import check
for pkg in numpy torch transformers; do python3 -c "import $pkg; print('$pkg', getattr($pkg,'__version__','OK'))" 2>&1; done

# Batch CLI check
for cmd in wine proton engrampa xfce4-terminal wmctrl; do which "$cmd" 2>&1 || echo "MISSING: $cmd"; done

# Linked-file cross-check
# skill_view returns linked_files dict; for each path, test -e against skill_dir
```

## Windows-path regex (corrected — avoids URL false positives)

```python
import re
# UPPERCASE drive letter + negative lookbehind: skips https://, steam://, etc.
WINDOWS_PATH_RE = re.compile(r"(?<![A-Za-z])[A-Z]:[\\/][\\/A-Za-z0-9_ .-]+")

def find_windows_paths(text):
    return WINDOWS_PATH_RE.findall(text)
```

PITFALL: a naive `[A-Za-z]:[\\/]` catches URL schemes. The negative lookbehind `(?<![A-Za-z])` + uppercase-only drive letter `[A-Z]:` cleanly separates `C:\Users` from `https://`.

## Audit pitfall: prose-vs-command on `hermes` subcommands

Skills frequently use "hermes agent", "hermes terminal", "a hermes container" as DESCRIPTIVE PROSE. Do NOT flag these as invalid subcommands. Test: would this run as `hermes <word> ...` in a shell? If it sits mid-sentence ("hermes errors out and exits"), it's prose. Use `hermes --help` to get the real subcommand list, and only flag `hermes <word> --help` → "invalid choice" patterns that appear in code blocks / shell instructions.

## Deliverable

Output a STATUS_HERMES_SKILL_AUDIT.md with:
- Per-skill PASS/WARN/FAIL with evidence from live checks
- Windows-path summary (which skills, gated vs raw)
- Missing dependency table (package, needed by, status)
- Redundancy pairs with merge recommendation
- Fixes needed, priority-ordered