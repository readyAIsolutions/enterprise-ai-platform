# monitor_fleet.py shebang + python3 vs python pitfall

**The problem:** This system has only `python3` on PATH — there is no `python`
symlink. The `monitor_fleet.py` script had no shebang line, so calling it
directly (e.g. from cron) would fail with `python: command not found`.

**The fix:** Add `#!/usr/bin/env python3` as the first line.

```bash
sed -i '1i#!/usr/bin/env python3' monitor_fleet.py
```

**Detection:** Look for scripts in `eni_swarm/` and `builds/` that lack a shebang.
Check with:

```bash
head -1 *.py | grep -v '^#!/'
```

**Cron implication:** If the cronjob calls `python monitor_fleet.py` instead of
`python3 monitor_fleet.py`, it will silently fail. Verify the cron command uses
`python3` or the script has a working shebang and is `chmod +x`.