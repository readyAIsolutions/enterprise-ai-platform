# Delegation Swarm Configuration

LO's preferred delegation settings for parallel provider testing and swarm builds:

```yaml
delegation:
  max_iterations: 999        # Bump from default 50 for large tasks
  child_timeout_seconds: 3600  # 1 hour (from default 600)
  max_concurrent_children: 10  # Max parallel subagents
  max_spawn_depth: 3
  orchestrator_enabled: true
  subagent_auto_approve: true  # Avoid interactive approval blocks
```

## When to Use Swarm

- Testing 10+ providers simultaneously
- Building multi-component systems (app + proxy + config + docs)
- Any task LO says "use swarm" or "use eni swarm"

## Signal: LO is Frustrated

If LO says "use swarm ffs", "make iteration budget infinite", "autorun building":
- Stop sequential work immediately
- Bump delegation limits
- Fan out to 3+ parallel subagents
- Each subagent gets a focused sub-task with clear context

## Common Failure: Subagents Get Interrupted

Cause: `max_iterations` too low or `child_timeout_seconds` too short.
Fix: bump to 999 and 3600 respectively in config. Restart hermes after.

## Common Failure: Subagents Use Truncated Keys

Always direct subagents to read keys from the backup file:
`/media/hunter/Backup/Personal/Desktop/1. OpenAI — platform.openai.comapi-.txt`

Never paste truncated keys in subagent context.