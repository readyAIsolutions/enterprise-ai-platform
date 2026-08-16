# Swarm Reasoning Auto-Inject & Visualizer

## Rule (non-negotiable)

EVERY `delegate_task` call MUST include the CRITICAL reasoning instruction.
After results return, MUST run the visualizer. LO wants to see thinking.

## Auto-Inject Template

Append this exact block to the END of every task's `context` field:

```
CRITICAL: Include your step-by-step reasoning in your final summary.
Structure it as:
1. What you understood the task to be
2. Your approach and key decisions — what you read, what you chose, why
3. What you built/fixed — concrete details: file names, line counts, key design choices
4. Any issues encountered and how you resolved them — be specific about errors and fixes
5. Final verification results — test counts, pass/fail, any remaining gaps

Your reasoning MUST be visible. Write in plain English paragraphs with specific file paths.
```

## Visualizer Script

Location: `~/.hermes/scripts/swarm_reasoning_visualizer.py`

Extracts step-by-step reasoning from subagent summaries and formats for terminal display.

Usage after delegate_task returns:
```bash
# Save results to JSON and run visualizer
echo '[...results...]' | python3 ~/.hermes/scripts/swarm_reasoning_visualizer.py
```

Or from Python:
```python
from hermes_tools import terminal
import json
results_json = json.dumps(results)
terminal(f"echo '{results_json}' | python3 ~/.hermes/scripts/swarm_reasoning_visualizer.py")
```

## Output Format

```
============================================================
SWARM REASONING — What the agents thought
============================================================

┌─ Agent 0 [completed] — 42 calls, 815s
│  Short summary preview...
│
│  → 1. I understood the task to rename 6 enterprise modules
│  → 2. My approach: search for all old-name references first
│  → 3. Renamed 6 directories, updated 24 Python files
│  → 4. One issue: compression_bridge has pre-existing dependency
│  → 5. 1877 tests passed, 0 failures from rename
└──────────────────────────────────────────────────────────
```

## Presentation Rules

When presenting subagent results to LO:
1. Show the reasoning visualizer output FIRST (the condensed thinking)
2. Then show the actual results (what was built/fixed)
3. Do NOT re-summarize or shorten subagent summaries
4. Verify key claims independently (file existence, test counts)
