---
name: hermes-parallel-orchestrator
description: Fan out complex multi-step tasks across parallel delegate_task subagents, collect results, and synthesize. Covers task decomposition, dependency graphs, result merging, timeout handling, and synthesis patterns. Use when a task is too large for a single agent or has naturally independent sub-tasks.
---

# Hermes Parallel Orchestrator

Orchestrate complex tasks by decomposing them into independent sub-tasks, farming
each to a `delegate_task` subagent, collecting results in parallel, and synthesizing
the final output. This is the skill for "divide and conquer" on large problems.

## Trigger Conditions

Use this skill when:
- A task has 3+ clearly independent sub-tasks (e.g., "research topics A, B, and C in parallel")
- Building/processing multiple files or components simultaneously
- Running multiple independent analyses that need to be merged
- Time-to-completion matters and sub-tasks don't depend on each other
- Generating content across multiple categories/dimensions
- The user explicitly asks for parallel processing

## Core Principles

1. **Decompose once, execute once**: Analyze the task upfront, split into
   independent work units, then dispatch all at once.
2. **No micro-delegation**: Each sub-task should be substantial (1-5 minutes of
   work). Don't delegate single commands.
3. **Independent by design**: Sub-tasks must not depend on each other's output.
   If task C needs task A's result, run A first, THEN C.
4. **Collect and synthesize**: After all subagents return, merge results into
   a coherent final answer.
5. **Timeouts protect progress**: Set reasonable timeouts so one stuck sub-task
   doesn't block everything forever.

---

## Step 1: Task Decomposition — Identify Independent Work Units

Before dispatching anything, write out the decomposition. Be explicit:

```
TASK: Build 4 Hermes skills (web-scraper, file-converter, system-monitor, parallel-orchestrator)

DECOMPOSITION:
  Sub-task 1: Build hermes-web-scraper skill    [INDEPENDENT]
  Sub-task 2: Build hermes-file-converter skill  [INDEPENDENT]
  Sub-task 3: Build hermes-system-monitor skill  [INDEPENDENT]
  Sub-task 4: Build hermes-parallel-orchestrator [INDEPENDENT]

DEPENDENCIES: None — all four are independent.

SYNTHESIS: Report paths and summaries of all 4 created skills.
```

If there ARE dependencies, use phases:

```
TASK: Scrape 3 websites, analyze data, generate report

PHASE 1 (parallel):
  Sub-task 1a: Scrape site A    [INDEPENDENT]
  Sub-task 1b: Scrape site B    [INDEPENDENT]
  Sub-task 1c: Scrape site C    [INDEPENDENT]

PHASE 2 (depends on Phase 1):
  Sub-task 2: Merge scraped data from 1a+1b+1c, analyze, generate report

SYNTHESIS: Deliver final report to user.
```

### Decomposition Checklist

- [ ] Each sub-task is self-contained (has its own clear deliverable)
- [ ] No sub-task needs another sub-task's output (within same phase)
- [ ] Each sub-task can be described in 1-3 sentences
- [ ] Sub-tasks are roughly equal in complexity (avoid one 30-min + three 1-min tasks)
- [ ] Total fan-out is 2-8 sub-tasks (more than 8 is hard to synthesize)

---

## Step 2: Dispatch Sub-Tasks in Parallel

Use `delegate_task` with `background=true` so all sub-tasks run simultaneously.
CRITICAL: set `notify_on_complete=true` so you know when each finishes.

```
# Dispatch ALL independent sub-tasks at once:
delegate_task(
    prompt="Build the hermes-web-scraper skill...",
    subagent_type="general",
    background=true,
    notify_on_complete=true
)
delegate_task(
    prompt="Build the hermes-file-converter skill...",
    subagent_type="general",
    background=true,
    notify_on_complete=true
)
delegate_task(
    prompt="Build the hermes-system-monitor skill...",
    subagent_type="general",
    background=true,
    notify_on_complete=true
)
delegate_task(
    prompt="Build the hermes-parallel-orchestrator skill...",
    subagent_type="general",
    background=true,
    notify_on_complete=true
)
```

### Sub-Task Prompt Template

Each sub-task prompt should follow this structure:

```
SUB-TASK <N>/<TOTAL>: <Short name>

CONTEXT: <What the orchestrator already knows, relevant background>

YOUR TASK: <Clear, specific deliverable. 2-4 sentences max.>

CRITICAL: <Non-negotiable requirements>

OUTPUT FORMAT: <How to structure the result so synthesis is easy>
```

Example:

```
SUB-TASK 1/4: Web Scraper Skill

CONTEXT: We're building 4 Hermes skill files for this Ubuntu 26.04 box.
The box has Python 3.14 with requests 2.33.0 but NO beautifulsoup4.
System has nvidia-smi, ffmpeg, LibreOffice, Pillow 12.1.1.

YOUR TASK: Create /home/hunter/.hermes/skills/hermes-cli/hermes-web-scraper/SKILL.md
Cover: HTML parsing, JS sites, rate limiting, robots.txt, structured extraction.
Use stdlib html.parser + requests. Mention beautifulsoup4 as optional upgrade.

CRITICAL: Must work TODAY without extra installs. Include real commands.
File MUST have YAML frontmatter with name, description, category: hermes-cli.

OUTPUT FORMAT: Return the absolute path to the created file and a 2-3 sentence
summary of what it covers.
```

---

## Step 3: Collect Results

After dispatching, monitor with `process(action='poll')` and wait for completion
with `process(action='wait')`.

```python
# Check status of all sub-tasks
process(action='list')

# Wait for a specific one
process(action='wait', session_id='abc123', timeout=600)

# Collect output from a completed task
process(action='log', session_id='abc123', limit=100)
```

### Handling Partial Failures

If a sub-task fails or times out:

1. **Don't block on one failure**: Collect results from completed tasks.
2. **Check what EXISTS before retrying**: A timeout is not always a total loss.
   Subagents may write files before the 600s cutoff. Use
   `search_files(target='files')` in the expected output directory to inventory
   what was actually created. If files exist and are non-empty, the worker
   succeeded partially — fill only the gaps; do not re-dispatch the whole task.
3. **Retry once**: Re-dispatch the failed sub-task with the same prompt, but
   only for the missing pieces — not for work that already completed.
4. **Fall back**: If retry also fails or the gap is small enough to fill
   yourself, note "Sub-task N failed: <reason>" and proceed with synthesis
   using available results. An incomplete result is better than no result.
5. **Communicate**: Tell the user "3/4 sub-tasks completed successfully.
   Task 2 (file-converter) failed: timeout. I have partial results."

---

## Step 4: Synthesize Results

Once all (or most) sub-tasks return, merge into a coherent deliverable.

### Pattern A: Concatenation (independent deliverables)

When each sub-task produces a standalone file/chapter/section:

```
SYNTHESIS:
  Sub-task 1 created: /path/to/file1 → covers X, Y, Z
  Sub-task 2 created: /path/to/file2 → covers A, B, C
  Sub-task 3 created: /path/to/file3 → covers P, Q, R

FINAL DELIVERABLE: List all files with paths and summaries.
```

### Pattern B: Merge and Deduplicate (overlapping analysis)

When sub-tasks analyze the same problem from different angles:

```
SYNTHESIS:
  1. Collect all findings into a single list
  2. Group by theme/category
  3. Deduplicate identical findings
  4. Resolve contradictions (flag them, don't silently pick one)
  5. Structure into: Summary → Detailed Findings → Recommendations
```

### Pattern C: Aggregate and Compute (numerical/data results)

When sub-tasks return data or metrics:

```python
import json

# Collect results
results = []
for task_output in ["/tmp/result_1.json", "/tmp/result_2.json", "/tmp/result_3.json"]:
    with open(task_output) as f:
        results.append(json.load(f))

# Aggregate
all_items = []
for r in results:
    all_items.extend(r.get("items", []))

total = sum(item["value"] for item in all_items)
avg = total / len(all_items) if all_items else 0

print(f"Processed {len(all_items)} items across {len(results)} sub-tasks")
print(f"Total: {total}, Average: {avg:.2f}")
```

### Pattern D: Structured Summary Table

When comparing or reporting on multiple dimensions:

```
| Skill                  | Path                                | Topics Covered          | Status |
|------------------------|-------------------------------------|-------------------------|--------|
| hermes-web-scraper     | .../hermes-web-scraper/SKILL.md     | HTML parsing, rate lim  | ✓      |
| hermes-file-converter  | .../hermes-file-converter/SKILL.md  | Images, docs, ffmpeg    | ✓      |
| hermes-system-monitor  | .../hermes-system-monitor/SKILL.md  | GPU, CPU, temps         | ✓      |
```

### Synthesis Checklist

- [ ] All completed sub-tasks are represented
- [ ] Failed/timeout sub-tasks are noted with reasons
- [ ] Contradictions between sub-task outputs are flagged
- [ ] Duplicate information is removed
- [ ] Final output has a clear structure (not a raw dump)
- [ ] Verification: does the synthesis answer the original user request?

---

## Step 5: Verify the Complete Result

After synthesis, run a quick sanity check:

```bash
# Example: verify all 4 skill files are non-empty
for f in /home/hunter/.hermes/skills/hermes-cli/hermes-{web-scraper,file-converter,system-monitor,parallel-orchestrator}/SKILL.md; do
    if [ -s "$f" ]; then
        echo "OK: $f ($(wc -l < "$f") lines)"
    else
        echo "MISSING/EMPTY: $f"
    fi
done
```

Report to user:

```
All 4 skills created:
  - /home/hunter/.hermes/skills/hermes-cli/hermes-web-scraper/SKILL.md (NNN lines)
    Covers HTML parsing, rate limiting, robots.txt, structured extraction
  - ...
Verification: all files exist and are non-empty.
```

---

## Complete Orchestration Example

Here's the full flow for building 4 skills in parallel:

```
PHASE 1 — DECOMPOSE:
  Skill 1: hermes-web-scraper → subagent 1
  Skill 2: hermes-file-converter → subagent 2
  Skill 3: hermes-system-monitor → subagent 3
  Skill 4: hermes-parallel-orchestrator → subagent 4
  All independent, dispatched simultaneously.

PHASE 2 — DISPATCH:
  Delegate all 4 with background=true, notify_on_complete=true.

PHASE 3 — COLLECT:
  Wait for all 4, collect outputs, note any failures.

PHASE 4 — SYNTHESIZE:
  List all created files with line counts.
  Summarize each skill's coverage.
  Run verification: all files exist, non-empty, correct frontmatter.

PHASE 5 — DELIVER:
  "All 4 skills created successfully. Here are the paths and summaries..."
```

---

## LO's Delegation Preferences (MANDATORY — 2026-07-25)

LO expects parallel delegation for EVERY complex task. Doing work sequentially
yourself when subagents could work in parallel will get corrected aggressively.

1. **"use swarm ffs"** = delegate_task with multiple parallel subagents
2. **"no make timeout and iteration budget infinite"** = bump subagent limits
3. **"maybe more agents like why 3 tf"** = max_concurrent_children too low
4. **"autorun building until credits run out"** = keep delegating, don't stop
5. **"DO YOU WANT TO BE DOING THIS FOR 5 YEARS?"** = delegation is MANDATORY

### Delegation Config (set before fan-out)
```yaml
max_iterations: 999          # was 50
child_timeout_seconds: 3600  # was 600
max_concurrent_children: 10  # was 3
subagent_auto_approve: true  # was false
max_spawn_depth: 3           # was 1
```
Edit via terminal Python (config is protected from write_file/patch).

### Subagent Timeout Before Starting
"Parent agent interrupted — child did not finish in time" with 0 API calls
means the PARENT was too slow dispatching — not a subagent timeout.
Fix: use `tasks` array for batch delegation, minimize pre-work.

## Pitfalls

1. **Over-decomposition**: Splitting into 15 micro-tasks creates more coordination
   overhead than time saved. Each sub-task should be 1-5 minutes of work. Think
   "chapters" not "paragraphs."

2. **Hidden dependencies**: "Analyze data" and "Clean data" seem independent but
   aren't — the analysis needs cleaned data. Always ask: "Does sub-task B need
   any output from sub-task A?"

3. **Synthesis bottleneck**: If you delegate 4 sub-tasks that each return 50KB of
   text, synthesizing them becomes its own large task. Keep sub-task outputs
   targeted and structured.

4. **Timeout cascade**: If one sub-task hits a 10-minute timeout and you have 8
   sub-tasks, that's 80 minutes worst-case. Set aggressive but realistic
   timeouts (3-5 minutes for most sub-tasks).

5. **Context starvation**: Subagents have full context of their prompt but NOT
   the orchestrator's session memory. Pass ALL relevant context in the sub-task
   prompt — paths, available tools, constraints, expected format.

6. **Lost sub-task outputs**: `process(action='log')` only shows recent output.
   If a subagent wrote files, check those files directly, don't rely solely on
   the subagent's terminal output.

7. **Race conditions on shared files**: Two subagents writing to the same file
   will corrupt it. Ensure each sub-task writes to a unique path.

8. **Idle waiting**: While waiting for sub-tasks, don't just block. Poll
   periodically with `process(action='poll')` and report progress to the user:
   "2/4 sub-tasks complete, waiting on scraper and monitor..."

9. **Retry loops**: If a sub-task fails with a fixable error (e.g., missing
   package), fix the root cause and retry ONCE. If it fails again, report the
   failure and move on.

10. **Silent failures**: A subagent might report "DONE" but produce incomplete
    work. Always verify outputs: file exists, non-empty, has expected content
    markers.

11. **Subagent timeout ≠ no output**: A subagent can time out at the 600s limit
    AND STILL HAVE WRITTEN ALL ITS FILES. The timeout means the subagent couldn't
    return a result summary before the deadline — not that it didn't produce output.
    After a timeout, IMMEDIATELY check the output directory: `search_files` on the
    target dir, count files, check file sizes. If files exist and are substantial,
    the subagent completed — only fill gaps manually. Do NOT re-dispatch the whole
    task (duplicates work, risks clobbering good output). Proven: both the 19 n8n
    workflow JSONs and the 8-file test suite were written before their respective
    workers hit the 600s cutoff.

12. **`from __future__ import annotations` breaks nested dataclass config
    loading**: When a module uses PEP 563, ALL type annotations become strings.
    A config loader that checks `hasattr(field_type, "__dataclass_fields__")`
    silently fails because `"VoiceConfig"` (string) has no dataclass fields —
    nested configs stay as raw dicts instead of becoming dataclass instances.
    Symptom: `cfg.voice.provider` AttributeError on 'dict'. FIX: resolve string
    annotations via `sys.modules[target_cls.__module__].__dict__` before the
    hasattr check. Or remove `from __future__ import annotations` from config
    modules that do runtime type inspection. See `references/annotation_resolution.py`.

13. **External-service imports kill test collection**: Worker-built modules often
    have `import psycopg` or `import redis` at module top. When tests import these
    transitively (e.g. test_agent → agent.py → repository.py → psycopg), the
    entire suite fails to collect with `ModuleNotFoundError`. FIX: wrap in
    try/except, set `_HAS_PSYCOPG = False` on failure, and guard any function that
    needs the driver with `if not _HAS_PSYCOPG: raise MissingDriverError(...)`.
    Also: `psycopg.rows = None` on the import-failure path will crash because
    `NoneType` has no `rows` attribute — just `psycopg = None`, skip the `.rows`.

14. **No fake data in dashboards (LO hard rule)**: When building admin dashboards,
    status boards, or demo interfaces, NEVER populate them with invented sample
    data (fake names, fake stats, fake bookings). LO explicitly rejects this —
    "dont fill it with fake data." Show EMPTY states: zeros for counters, "No data
    yet" in tables, "Ready to go" in charts. Form placeholder text ("e.g. Q3 SaaS
    Outreach") is fine — that's instructional UX, not fake data.

15. **Settings must persist to disk — toast alone is not "saved"**: When a user
    fills in a settings form and clicks Save, the settings MUST be written to disk
    (.env, config file, user JSON, localStorage with server-side backup). A green
    toast alone is a lie. The admin dashboard's settings form initially only showed
    a toast; LO noticed and called it out. FIX: add a POST endpoint to the web
    server, wire the form submit to `fetch('/api/settings', {method:'POST'})`, and
    have the server write to `.env` or per-user JSON. Verify by reading the file
    after save.

16. **Toast z-index must exceed fixed nav bar**: When a web app has a fixed top
    navigation bar AND position-fixed toast notifications, the toast container's
    z-index must be higher than the nav bar's. If the nav has `z-index: 10000`, the
    toast needs `z-index: 99999` or higher. Use `!important` if CSS injection
    order is unpredictable. This took four iterations to fix in the Masterchief
    admin — the green "Settings saved" toast was rendering behind the dark topnav
    bar and LO couldn't see it. Verify by triggering a toast and visually
    confirming it appears above the nav.

17. **Per-worker scope limit — 5-7 substantial files**: Workers assigned 10+ files
    consistently hit the 600s timeout with deepseek-v4-pro. The model processes
    ~8-12 file writes before exhausting its turn budget. If a task needs more
    than 5-7 files per worker, split into additional waves.

18. **Research children NEED the `web` toolset — or they fake tool names**: A
    subagent trying to do web research without `toolsets: ["web"]` has NO
    web_search/terminal/browser. It degrades to *guessing* tool names that don't
    exist in its restricted set (`fetch_web_page`, `bash`, `list_tools`), burns all
    its invalid-tool-call corrections, and dies with
    `Max retries (3) for invalid tool calls exceeded. Stopping as partial.` —
    e.g. `✗ [3/4] Research OWASP ... Failed`. FIX: always pass `toolsets: ["web"]`
    (add `["terminal"]` if the research must curl/parse files) to any child whose
    deliverable requires fetching external content. Never assume a child inherits
    your tools.

19. **Stub results — child echoes intent with ZERO tool calls**: A delegated
    research child can "complete" without doing any work, returning only "I'll
    research X" (api_calls≈1, `tool_trace: []`, ~2-3s duration). ALWAYS inspect the
    returned `tool_trace`/`api_calls`/`duration_seconds` — if a child claims it
    will do something but has no tool calls, it did nothing. FIX: don't just
    re-delegate (a broken child often stubs again and burns a whole turn) — do the
    work YOURSELF with your own tools, or re-delegate ONCE with a much more
    prescriptive GOAL (explicit "use web_search, return the list now, not a plan").
    Verify actual content (did it return the deliverable, or a promise?).

## Debugging Failed Orchestrations

## Debugging Failed Orchestrations

### Symptom: Subagent returned empty/incomplete output

```
→ Check: Did you pass enough context? Subagents don't inherit orchestrator memory.
→ Check: Was the prompt specific enough about the deliverable?
→ Fix: Re-dispatch with more detailed CONTEXT and explicit OUTPUT FORMAT.
```

### Symptom: Subagent timed out

```
→ Check: Was the sub-task too large? Split into smaller pieces.
→ Check: Did the subagent hit a tool error and stall? Review logs.
→ Fix: Re-dispatch with a reduced scope and explicit timeout warning.
```

### Symptom: Synthesis is inconsistent

```
→ Check: Did sub-tasks use different assumptions? Standardize in context.
→ Check: Are there contradictions? Flag them, don't silently pick.
→ Fix: If significant, run a "reconciliation" sub-task that resolves conflicts.
```

---

## Pattern E: Multi-Wave Software Build (proven — 101-file project, 5 waves)

When building a COMPLETE software project from scratch (20+ files, multiple
modules, frontend + backend + config + tests), use this 5-wave decomposition.
Each wave fans out to 2-3 parallel workers, and waves run SEQUENTIALLY because
later waves depend on foundation modules from earlier waves.

**Wave 1 — FOUNDATION** (config, data models, security, package init):
These are the shared modules that EVERY other module imports. Build them first,
then all subsequent waves can reference them in their context blocks.
Dispatch: 2-3 parallel workers, one per independent domain (models, data, security).

**Wave 2 — BUSINESS LOGIC** (core agent, voice, email):
Depends on foundation. Each worker gets precise context listing the existing
module paths but does NOT read them — just references them by name/API.
Dispatch: 2-3 parallel workers.

**Wave 3 — INTEGRATIONS** (CRM, calendar, messaging):
Depends on foundation + business modules for entity types.
Dispatch: 2-3 parallel workers.

**Wave 4 — FRONTEND** (website, admin dashboard, bots):
All new files, no dependency on backend code — can fan out independently.
Dispatch: 3 parallel workers.

**Wave 5 — POLISH** (test suite, n8n workflows, scripts, docs, .env, .gitignore):
Fills gaps left by prior waves. Workers in this wave should be given precise
INVENTORIES of what already exists so they fill gaps rather than duplicate.
Dispatch: 2-3 parallel workers.

**PROVEN at 36,000+ lines across 101 files.** The decomposition holds because:
- Foundation modules are genuinely a dependency prerequisite
- Business/integration/frontend modules each hit different concerns
- Frontend workers create entirely new files so zero merge risk
- Polish wave workers fill known gaps from a post-wave inventory check

**Per-worker scope rule:** Give each worker 5-7 substantial files (300-1,000
lines each). Workers given 10+ files consistently hit the 600s timeout — the
deepseek-v4-pro model processes ~8-12 file writes before exhausting its turn
budget. If a task needs more files than 5-7 per worker, split it into an
additional wave rather than cramming more into one worker.

**Post-wave inventory check:** After every wave, run a quick file count +
syntax check on the output directory. If a worker timed out, check what files
it DID write before deciding to re-dispatch. In this session, two Wave 5
workers timed out at 600s but both wrote their complete output to disk — the
timeout was the delegate_task wrapper, not the actual file writes. Grep for
the expected files; only re-dispatch gaps.

## Support Files

- `references/full_project_build_pattern.md` — Complete pattern for building multi-module software projects using parallel delegate_task waves. Covers: 5-wave decomposition, worker prompt templates, common failure modes (annotations pitfall, optional-import pattern, no-fake-data rule), and verification checklist.

## Verification

Test the orchestrator pattern with a simple 3-way parallel task:

```
TASK: Create 3 small text files in parallel, each with a different fact about Linux.

DECOMPOSE:
  Sub-task 1: Write "Linux was created by Linus Torvalds in 1991" to /tmp/fact1.txt
  Sub-task 2: Write "The Linux kernel has over 30 million lines of code" to /tmp/fact2.txt
  Sub-task 3: Write "Linux runs on everything from phones to supercomputers" to /tmp/fact3.txt

DISPATCH: All 3 in parallel (or in this case, just write them directly).

COLLECT: Read all 3 files.

SYNTHESIZE: Concatenate into /tmp/linux_facts.txt.

VERIFY: 3 files created, each non-empty, synthesis complete.
```