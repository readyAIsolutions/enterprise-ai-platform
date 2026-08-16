# Efficient FIFO / STATUS verification (avoid 300s hangs)

When reconciling IDLE state a builder must (a) confirm its control FIFO
`/tmp/eni_ctl_<NAME>` is absent and (b) locate + read its `STATUS_<NAME>.md`.
Two real 300s-timeout traps were hit in BUILD_37 reconciliation (Aug 2026) —
these are the affordable ways to do it.

## 1. FIFO existence — use os.path.exists ONLY, never read
The control channel is a named pipe, not a regular file. `cat`/`read_file`/
`head`/`tail` on an existing-but-unwritten FIFO BLOCKS INDEFINITELY (this
already costs one full tool timeout). The cheap, safe probe is:

```python
import os, stat
p = '/tmp/eni_ctl_BUILDER_37'
exists = os.path.exists(p)
is_fifo = exists and stat.S_ISFIFO(os.stat(p).st_mode)
```
Wrap it in a short `execute_code` block. Do NOT `cat` to "check for work".

## 2. Locating STATUS_<NAME>.md — use search_files, NOT recursive glob
Doing `glob.glob('/home/hunter/**/STATUS_BUILDER_37*', recursive=True)` inside
`execute_code` timed out at 300s (the home dir is huge — site-packages,
Desktop, caches). Likewise `glob.glob('/tmp/**/*BUILDER_37*', recursive=True)`
risks walking into a blocking socket/FIFO under `/tmp` (e.g.
`hermes_rpc_*.sock`).

Correct, fast, hang-free:
```
search_files(target='files', path='/home/hunter/Desktop', pattern='STATUS_BUILDER*')
search_files(target='files', path='/tmp', pattern='STATUS_BUILDER*')
```
Target a narrow root (the swarm dir, not the whole home dir). Returns in
milliseconds and never blocks on special files.

## 3. Reading STATUS — read_file, not cat
Once located, `read_file` the STATUS file normally. A correctly-reconciled
IDLE status looks like:
```
[IDLE]
verified=... no /tmp/eni_ctl_<NAME> FIFO; master driver not running (...)
blocker=none
next=await LO's directive; will process task the moment FIFO is created
```
If it already reads `[IDLE]`, leave it — do not rewrite config/Model lines.
Only rewrite the status line/timestamp/blocker/next if the file was stale.

## Rule of thumb
- FIFO probe: `os.path.exists` only.
- STATUS search: `search_files` with a targeted path.
- STATUS read: `read_file`.
Never `cat` a FIFO, never recursive-glob the whole home dir or `/tmp`.
