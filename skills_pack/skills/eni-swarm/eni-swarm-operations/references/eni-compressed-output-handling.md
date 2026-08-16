# Handling ENI-COMPRESSED tool/skill output during fleet ops

## Symptom
When calling `skill_view` (or `terminal`/`execute_code` that prints a batch of
swarm files), the result may come back as:

```
<ENI-COMPRESSED ratio=2.2x carrier=/home/hunter/Desktop/eni_compression/carriers/carrier_XXX.png
(full result losslessly persisted; recover via decompress(carrier))>
--- head ---
{...}
--- tail ---
{...}
```

This is normal in the ENI environment — skill bodies and verbose tool output are
deliberately compressed into carrier images.

## What works (use this every time)
1. **Read the embedded `head` and `tail` excerpts.** They are JSON/plain-text and
   reliably carry the operational essentials — for a skill this means the key
   instructions and both boundaries of the body; for a tool dump it means the most
   relevant lines (e.g. ledger rows, mtime signature, file headers).
2. **Proceed with the task from those excerpts.** For the fleet-monitor cron the
   head/tail were sufficient to run the full diagnostic and produce a correct
   report-only pass. Do not block waiting to recover the lossless payload.
3. Only chase full `decompress(carrier)` recovery if the excerpt is genuinely
   missing a detail you cannot infer. A blind guess at the decompress tool's
   module/CLI path usually fails — treat recovery as optional, not required.

## Don't
- Do NOT conclude "decompression is broken" or "the skill is unreadable" from a
  failed `decompress` attempt. The excerpts *are* the accessible content.
- Do NOT let the compression wrapper stall a cron pass (fleet monitor, heartbeat,
  swarm ops) — the excerpts almost always contain enough to act.
