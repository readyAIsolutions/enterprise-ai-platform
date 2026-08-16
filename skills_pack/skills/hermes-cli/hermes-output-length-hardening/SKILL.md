---
name: hermes-output-length-hardening
description: Fix Hermes "Response truncated due to output length limit" permanently — raise agent.max_output_tokens AND patch the five truncation retry caps in site-packages/agent/conversation_loop.py (the real wall), plus inject a completion-gating prompt for truncated tool calls. Use whenever a long build / delegation output gets cut off, or when a tool call ends in finish_reason='length'. Also ships a platform module `response_hardening` that audits+repairs automatically.
---

# Hermes Output-Length Hardening ("never truncated again")

## When to use
- "Response truncated due to output length limit" appears.
- A tool call (esp. `delegate_task` returning big JSON args) gets cut at
  finish_reason='length'.
- LO says "max the output limit the fuck out".

## Root cause (two DIFFERENT caps)
1. **Config cap** `agent.max_output_tokens` in `~/.hermes/config.yaml`.
   Default was 65536 (64K). This is the ceiling the agent aims at.
2. **Hard retry caps** in `site-packages/agent/conversation_loop.py` that decide
   how many times the loop recovers from a truncation before giving up:
   - `truncated_tool_call_retries < 1`  → the hard wall (only ONE retry then refuse)
   - `length_continue_retries < 3`
   - `_codex_incomplete_retries < 3`
   - `_invalid_json_retries < 3`
   - `_empty_content_retries < 3`

Even with config maxed, the OLD tool-call branch retried once then returned
`{"error": "Response truncated due to output length limit"}`.

## Fix steps
### 1. max the config
```bash
hermes config set agent.max_output_tokens 262144
grep -n max_output_tokens ~/.hermes/config.yaml   # expect 262144
```
Any number up to what the provider/model supports. 262144 (256K) is a good max.

### 2. patch the 5 retry caps (installed package)
File: `/home/hunter/.local/lib/python3.14/site-packages/agent/conversation_loop.py`
(or locate via `python3 -c "import agent.conversation_loop, os; print(agent.conversation_loop.__file__)"`)

Change all five `... < N` comparisons to `... < 8`. For the tool-call branch ALSO
inject a completion-gating prompt right before `continue` so the model RESUMES the
cut JSON arguments instead of re-issuing the same oversized call:

```python
if truncated_tool_call_retries < 8:
    truncated_tool_call_retries += 1
    agent._buffer_vprint(
        f"⚠️  Truncated tool call detected — instructing JSON completion ({truncated_tool_call_retries}/8)..."
    )
    messages.append({"role": "user", "content":
        "[System: Your previous tool call returned truncated (incomplete) JSON "
        "arguments because it exceeded the output length limit. Do NOT re-issue "
        "the full original call. Resume EXACTLY from where the JSON arguments "
        "were cut off, complete the argument fields, and close the JSON with the "
        "final '}'. Keep the parameters compact. Emit ONLY the repaired call now.]"})
    continue
```

After editing: `python3 -m py_compile <file>` then
`python3 -c "import agent.conversation_loop"` to confirm import works.

## Durable fix — the `response_hardening` module (PREFERRED)
The enterprise platform now ships a kernel module that audit() + repair() this
automatically. Use it instead of hand-editing:

```bash
cd "/home/hunter/Desktop/Enterprise Builder/enterprise"
PYTHONPATH=$PWD python3 -c "from enterprise.modules.response_hardening import audit, repair; print(audit()); print(repair())"
```
- `audit()` returns each cap current/healthy + `repair_needed`.
- `repair()` raises all five to 8, ensures the completion patch, backs up the
  original to `.bak_response_hardening`, refuses invalid syntax. Idempotent.
- Register as PlatformOS module (auto-discovered) with
  `config_defaults={"auto_repair": False}` (safe: repairs only when you call it).
- Tests: `pytest enterprise/modules/response_hardening -q`

## Pitfalls
- Do NOT set the config ceiling above what the provider actually honors; the
  patch fixes the RECOVERY so real truncation is rare anyway.
- The caps are hard-coded ints; a `pip install -U hermes-agent` overwrites the
  file, so re-run `repair()` after upgrades (that's what the module's
  auto_repair is for).
- Mind trailing spaces in the sentinel patterns when patching file text.
- Output length that's *actually* caped by the model (e.g. OpenRouter per-model
  max_completion_tokens) still ends a response; the fix makes it avoid dead-ends,
  not lift a provider-side hard ceiling.

## Verification
- `audit()["ok"] is True` and `repair_needed is False`
- A previously-truncated long `delegate_task`/tool call now completes to a clean
  finish_reason="stop".
- 6/6 unit tests pass on the module.