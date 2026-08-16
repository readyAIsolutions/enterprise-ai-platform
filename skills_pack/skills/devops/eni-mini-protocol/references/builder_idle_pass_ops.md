# Builder idle-pass operations (verified on BUILDER_37, Aug 08 2026)

One-stop checklist for a dispatched builder's idle pass, plus the compressed-file
reading technique that the other references assume you know.

## THE COMPRESSED-FILE READING TECHNIQUE (spelled out, verified BUILDER_37, Aug 14 2026)
ENI skill/reference content is often delivered wrapped as `<ENI-COMPRESSED carrier=...png>`.
To actually READ that content:
  - DON'T bother decompressing the carrier PNG. Attempting it (e.g. `python3 /tmp/eni_dec2.py
    <carrier>.png`) frequently fails at the PIL load step with `OSError: cannot load this image`
    (carrier is a persisted artifact, not a reliably-decodable present image). It's a dead end.
  - INSTEAD, read the raw file directly from its on-disk path with `read_file`. The
    `references/*.md` and `scripts/*` files live uncompressed on disk at the skill path
    (e.g. `<skill_dir>/references/builder_idle_pass_ops.md`) and come through as PLAINTEXT in
    the file content. The SKILL.md body itself often still arrives wrapped, but the
    references/scripts are readable directly — that's where the operational detail lives.
  - The skill_view → linked_files listing gives you the file names; resolve the real paths under
    `~/.hermes/skills/...` and `read_file` them directly. This is the reliable path.

## FAST PATH — run the verifier script FIRST (verified BUILDER_37, Aug 13 2026)

For a steady-state idle pass, do NOT hand-probe (ls /tmp/eni_ctl_*, stat each mirror,
date arithmetic). Run the packaged verifier directly — it subsumes ALL of it:

    bash <skill>/scripts/check_builder_idle.sh <BUILDER_NAME>   # e.g. BUILDER_37

Confirmed absolute path (verified BUILDER_37, Aug 13 2026):
    /home/hunter/.hermes/skills/devops/eni-mini-protocol/scripts/check_builder_idle.sh
If the deployment has moved and that path 404s, locate via find rather than hand-probing:
    find /home/hunter -maxdepth 8 -name 'check_builder_idle.sh' 2>/dev/null

It does the FIFO check (absent pipe = IDLE candidate) AND scans all five STATUS
mirrors (tokenizing both markdown H1 `STATUS_... — IDLE` and the `.cache` INI
`status=[IDLE]`) in one shot. Interpretations:
  - exit 0 + "Found=5/5 Missing=0/5 Idle=5/5 ... steady-state, nothing changed"
    => commit to [SILENT] directly. No reconcile, no rewrite work.
  - exit 1 => not all mirrors agree on IDLE (missing and/or a mirror not IDLE).
    Reconcile all five, then re-run to confirm exit 0.
  - exit 3/4 => FIFO present; directive may be pending — do NOT treat as idle.

KEY STEADY-STATE FACT: the five mirrors need NOT share an mtime to be healthy. The
verifier only checks that each tokenizes IDLE; different mtimes between mirrors
(e.g. one Desktop satellite refreshed hours later, the .cache INI older) is normal
and still exit 0. Only time-based reconcile matters when the check script itself
reports a non-IDLE or missing mirror.

## Corroborate "no directive pending" beyond the status mirrors (verified BUILDER_37, Aug 11 2026)
When a cron pass concludes IDLE, don't rely on the STATUS_BUILDER_* mirrors alone — the
mirrors only prove the last pass wrote IDLE, not that no directive is in flight. Cross-check
THREE independent corroboration sources before committing to [SILENT]:
  1. `tasks/swarm/<NAME>.txt` — the builder's role file states "If idle, write [IDLE]", and
     it is static (no live directive embedded). Its presence + static content = idle contract.
     EXACT PATH (verified BUILDER_37): `~/Desktop/Enterprise Builder/ENI_Swarm_NEW/tasks/swarm/<NAME>.txt`
     (e.g. BUILDER_37.txt, and siblings BUILDER_02/18/19/26/27/28/31/33/44/45). Use
     `find ~ -path "*tasks/swarm*BUILDER*.txt"` to locate it if the deployment has moved
     again. Its content is a static directive-monitor contract ("Monitor /tmp/eni_ctl_<NAME>.
     Write STATUS_<NAME>.md. If idle, write [IDLE].") — presence + static content = idle contract.
  2. The control FIFO `/tmp/eni_ctl_<NAME>` — must be ABSENT (see `builder_control_fifo_idle.md`).
  3. The verifier script's 5-mirror scan must report all IDLE.

NOTE: the five STATUS mirror paths baked into `check_builder_idle.sh` ARE correct/current
(BUILDER_37 scan: Found=5/5 Idle=5/5); only the role-file corroboration path differs from
the earlier doc — the script checks mirrors, not the role file, so verify the role file
separately (step 1 above).
