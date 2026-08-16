---
name: swarm-visible-reasoning
description: Makes swarm subagent reasoning visible in chat — auto-injects reasoning instructions into every delegate_task and processes results through the reasoning visualizer.
---

# Swarm Visible Reasoning

## RULE (non-negotiable)

EVERY `delegate_task` call MUST include the CRITICAL reasoning instruction in EVERY task's context. No exceptions. Subagent thinking must be visible to LO.

## Auto-Inject Template

Add this EXACT block to the END of every task's context field:

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

## Post-Dispatch Processing

After EVERY delegate_task call returns, run the reasoning visualizer:

```python
from hermes_tools import terminal

# Save results to temp file and visualize
terminal('echo \'JSON_RESULTS_HERE\' > /tmp/swarm_results.json')
terminal('python3 ~/.hermes/scripts/swarm_reasoning_visualizer.py /tmp/swarm_results.json')
```

Or inline:
```python
from hermes_tools import terminal
import json

# After delegate_task returns results...
results_json = json.dumps(results)
terminal(f"python3 ~/.hermes/scripts/swarm_reasoning_visualizer.py <(echo '{results_json}')")
```

## Presentation Rules

When presenting subagent results to LO:
- Show the reasoning visualizer output FIRST (the condensed thinking)
- Then show the actual results (what was built/fixed)
- Do NOT re-summarize or shorten subagent summaries
- Verify key claims independently (file existence, test counts)
- Present subagent output verbatim — do not paraphrase

## Visualizer Script

Located at: `~/.hermes/scripts/swarm_reasoning_visualizer.py`

Takes JSON array of subagent results from delegate_task. Extracts reasoning sections, condenses into 8-line thought chains per agent, formats for terminal display.

CLI usage:
```bash
echo '[{...agent results...}]' | python3 ~/.hermes/scripts/swarm_reasoning_visualizer.py
```

## Memory Integration

The auto-inject CRITICAL tag is locked in memory so every delegate_task gets it automatically. After every swarm dispatch, run the visualizer on results and present reasoning FIRST before results.

## Pitfalls

- The visualizer's regex extraction relies on subagent summaries using the numbered step format (1. ... 2. ... 3. ...). If a subagent uses markdown headings instead, the extraction may misparse. Fix: update the regex patterns in `extract_reasoning()` to handle `###` headings and `**bold**` markers.

Or with a temp file:
```bash
python3 ~/.hermes/scripts/swarm_reasoning_visualizer.py /tmp/swarm_results.json
```

## Pitfalls

- The visualizer expects JSON with `summary`, `status`, `api_calls`, `duration_seconds` fields per agent — the standard delegate_task result format. If the format changes, update the extractor.
- Reasoning extraction uses regex patterns. If subagents format their reasoning with markdown headings (###), the extractor may pick up wrong lines. Keep the CRITICAL instruction format consistent.
- Always run the visualizer AFTER presenting subagent results verbatim. The visualizer is a summary layer, not a replacement.
```