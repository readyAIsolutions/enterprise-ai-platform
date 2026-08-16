# Tool-calling: parser must handle the model's actual JSON — verify results are REAL

## Symptom (found 2026-08-05 while testing a fine-tuned model)

The model emitted the correct tool-calling JSON, and the response claimed a tool
ran — but the returned data was **synthetic/hallucinated**, not real.
Example: user asked for controller status; response showed `"module1/module2/
module3", count 3` when the REAL controller had 47 real modules. The model had
invented a plausible-looking result instead of using a real one.

## Root cause: the server's tool-parser couldn't parse the model's JSON

`_parse_tool_calls` (airllm_server.py) matched:
- Pattern 1: **only** fenced ` ```json ... ``` ` blocks.
- Pattern 2: `\{[^{}]*"tool"[^{}]*\}` — **forbids any nesting**, so a real
  `{"tool": "controller_status", "arguments": {}}` (nested `{}` inside) never
  matched.

The fine-tuned model emits a plain, multi-line, UNFENCED JSON object (with
nested `arguments`). None of the patterns matched → `_parse_tool_calls` returned
empty → the tool was never dispatched → and because the model got no real
result, it **hallucinated** a fake "[Controller Status]" / "[Tool Output]" block.

Lesson: a model that "calls tools" proves nothing. Confirm the tool id was
actually parsed AND dispatched, and that the REAL endpoint result (not the
model's summary) came back.

## FIX: robust nested-JSON extractor

Scan every `{` and bracket-match to the matching `}` (respecting string
literals and escapes), then `json.loads` the candidate and keep objects with a
`"tool"` key. Add this as the highest-level pattern, then de-dupe (patterns 1/2/4
can each match the same call) before dispatch:

```python
for m in re.finditer(r"\{", text):
    depth = 0; in_str = False; esc = False
    for j in range(m.start(), len(text)):
        ch = text[j]
        if esc: esc = False; continue
        if ch == "\\": esc = True; continue
        if ch == '"': in_str = not in_str; continue
        if in_str: continue
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[m.start():j + 1]
                try:
                    call = json.loads(candidate)
                    if isinstance(call, dict) and "tool" in call:
                        calls.append({"name": call["tool"],
                                      "arguments": call.get("arguments", {})})
                except json.JSONDecodeError:
                    pass
                break
# then de-dupe calls by (name, sorted args) before executing
```

## Verification rule (the non-negotiable check)

After any agent/tool-calling change, do a REAL test and compare against the real
endpoint:
- `curl :8940/status` → note real values (e.g. 47 modules, real router health).
- Ask the model to call the tool and report the result.
- If the model's summary contains numbers that DON'T match the real endpoint,
  the parser still isn't executing the tool (or the model ignored the result) —
  do NOT accept it. This is how the hallucination was caught: the model said
  "3 modules", the real controller had 47.

For small fine-tunes this is worse: a 7B QLoRA reliably picks the right tool and
emits valid JSON, but is FLAKY at faithfully consuming the returned result. See
the `local-llm-finetuning` skill's "HONEST LIMITS" section. Keep tool execution
server-side and deterministic (fail-closed) and treat the model as the intent
layer only; never let the model be the sole authority over side effects.
