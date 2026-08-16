# Concrete fan-out recipe for a lint/type-gate cleanup swarm

Reusable sequence from the enterprise-ai-platform ruff cleanup (1631 -> 0 across
141 files, 14 workers, monotonic, no regressions). Adapt paths/names per repo.

## 1. Inventory your files (only the ones YOU changed / own)
```bash
cd <repo>
git diff --name-only <base_commit>~1 -- '*.py' > /tmp/swarm_files.txt
wc -l /tmp/swarm_files.txt
```

## 2. Per-file ruff counts (blank line = 0 findings = already clean)
```bash
while read f; do
  n=$(ruff check "$f" 2>/dev/null | sed -n 's/Found \([0-9]*\) errors.*/\1/p')
  echo "$n|$f"
done < /tmp/swarm_files.txt | sort -rn > /tmp/swarm_inventory.txt
```
Blank count means that file is already clean — keep those OUT of worker groups.

## 3. Load-balanced disjoint partition (greedy bin-pack by error count)
```python
import os
items=[]
for l in open('/tmp/swarm_inventory.txt'):
    if '|' not in l: continue
    try: n,f = l.split('|',1)
    except ValueError: continue
    n = int(n) if n.strip().isdigit() else 0
    if n>0: items.append((n,f.strip()))
items.sort(reverse=True)
N=14                       # ~ your batch concurrency cap
bins=[[] for _ in range(N)]; binsum=[0]*N
for n,f in items:
    i=min(range(N), key=lambda i: binsum[i]); bins[i].append((n,f)); binsum[i]+=n
os.makedirs('/tmp/swarm_groups', exist_ok=True)
for i,b in enumerate(bins):
    open(f'/tmp/swarm_groups/group_{i}.txt','w').write('\n'.join(
        f for _,f in sorted(b, key=lambda x:x[1]))+'\n')
    print(f"group_{i}: {len(b)} files, {binsum[i]} errs")
```
Put STRATEGY.md at /tmp/swarm_groups/STRATEGY.md (shared by all workers).

## 4. Fan out delegate_task batch
One task per group. Each task context must include:
- absolute repo path, its group file path, STRATEGY.md path
- hard rules: only edit files in YOUR group_<N>.txt; never change runtime
  behavior or public API signature; run `ruff check $(cat group.txt)` until
  "Found 0 errors"; then `pytest` sibling tests; report before->after per file
  and which rules fixed vs suppressed.
- end summary with the CRITICAL reasoning block (understood/approach/changed/
  issues+noqa/verification with real numbers).
Toolsets: ["terminal", "file"] (enough to edit + run ruff/pytest).

## 5. Orchestrator closes the tail
Swarm always leaves a small set (~10-30) — typically:
- `__init__.py` dead typing re-export shims (collapse `Any, Dict, Optional` -> `Any`)
- `# noqa` misplaced by an earlier `ruff format` reflow
- single-line defs / unused fixture args you must now hand-place noqas on
- one-shot UP007/UP031/F821 stragglers
Fix these yourself directly with patch()/terminal — the tail is too small to
justify another wave.

## 6. Verify (never trust self-reports)
```bash
ruff check $(cat /tmp/swarm_files.txt) --output-format concise | tail -1   # "All checks passed!"
ruff format --check $(cat /tmp/swarm_files.txt)                            # idempotent
pytest -q                                                                  # full gate, background+notify
git status --short | wc -l                                                 # no stray files
```
Confirm zero worker touched a file outside its group:
compare session-changed set vs the union of group files.
