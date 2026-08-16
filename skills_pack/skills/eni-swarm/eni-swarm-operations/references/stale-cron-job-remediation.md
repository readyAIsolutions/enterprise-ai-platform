# Stale ENI Builder Cron Job Remediation

## Detection signals

| Signal | How to check |
|---|---|
| Cron watcher fires but FIFO absent | `ls -la /tmp/eni_ctl_BUILDER_NN` — no named pipe, no regular file |
| Builder number not in provisioned set | `ls -la /tmp/eni_ctl_BUILDER_*` shows which builders actually exist |
| Cron completed count growing fast | `jobs.json` shows `completed` climbing with every check |

Not every `BUILDER_N` number is provisioned — gaps are normal. But a **running** cron job for a gap number is stale.

## Tracing a stale cron job

The Hermes cron system stores all jobs in:

```
~/.hermes/cron/jobs.json
```

Find the job by builder number or FIFO path:

```bash
grep -B5 -A10 'BUILDER_37\|builder.37\|enI_ctl_BUILDER_37' ~/.hermes/cron/jobs.json
```

Inspect the job record:
- **id**: used for output directory and references
- **name**: human-readable label
- **enabled**: if `true`, it's actively firing
- **state**: "scheduled" means running, "paused" means stopped
- **repeat.completed**: total executions so far
- **schedule**: how often it fires
- **created_at**: when it was created (stale indicator if old)
- **last_delivery_error**: often "no delivery target resolved" for orphaned builder jobs

## Output accumulation

Each cron job stores execution output at:

```
~/.hermes/cron/output/<JOB_ID>/
```

Check:
```bash
ls ~/.hermes/cron/output/<JOB_ID>/ | wc -l
du -sh ~/.hermes/cron/output/<JOB_ID>/
```

A stale once-per-minute cron running for days can accumulate **thousands of files** (14 MB+ is typical).

## Remediation procedure

### 1. Disable the cron job

Read `jobs.json`, set `enabled: false` and `state: paused`, and annotate with reason:

```python
import json
with open('~/.hermes/cron/jobs.json') as f:
    data = json.load(f)
for job in data['jobs']:
    if job['id'] == '<JOB_ID>':
        job['enabled'] = False
        job['state'] = 'paused'
        job['paused_reason'] = 'Stale: Builder N not provisioned. FIFO absent. Disabled on <DATE>.'
with open('~/.hermes/cron/jobs.json', 'w') as f:
    json.dump(data, f, indent=2)
```

Or use `jq` for a shell one-liner:
```bash
jq '(.. | select(.id? == "<JOB_ID>").enabled) = false' ~/.hermes/cron/jobs.json > /tmp/jobs_new.json && mv /tmp/jobs_new.json ~/.hermes/cron/jobs.json
```

### 2. Clean up accumulated output

```bash
rm -rf ~/.hermes/cron/output/<JOB_ID>/
```

This prevents the output directory from continuing to accumulate stale entries if the cron service still references the directory.

### 3. Verify

```bash
python3 -c "
import json
with open('~/.hermes/cron/jobs.json') as f:
    data = json.load(f)
for job in data['jobs']:
    if job['id'] == '<JOB_ID>':
        print(f'Enabled: {job[\"enabled\"]}, State: {job[\"state\"]}, Reason: {job.get(\"paused_reason\", \"N/A\")}')
"
```

## Prevention

When deprovisioning an ENI builder:
1. Remove the FIFO: `rm /tmp/eni_ctl_BUILDER_NN`
2. Find and disable its cron job in `jobs.json`
3. Verify no processes still reference the builder number