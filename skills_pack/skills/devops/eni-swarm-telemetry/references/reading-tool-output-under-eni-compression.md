# Reading fleet tool output when it arrives ENI-compressed

On LO's box, tool results (including `skill_view` on this skill, `read_file`,
and large terminal echoes) are frequently intercepted by the ENI compression
layer and returned as:

    <ENI-COMPRESSED ratio=Nx carrier=/home/hunter/Desktop/eni_compression/carriers/carrier_xxxx.png (full result losslessly persisted; recover via decompress(carrier))>
    --- head ---
    {"success": true, ... truncated ...}
    --- tail ---

This truncates the very template/probe text the fleet cron run needs VERBATIM
(the `fleet-cron-report.md` shape, the liveness-probe output format). Do NOT try
to reconstruct the report from the compressed head/tail fragments.

## Workaround that reliably works (used this session)

Read the raw file straight off disk with a shell one-liner instead of relying
on the tool-returned (compressed) content:

    # Verbatim report template (all 59 lines):
    sed -n '1,60p' ~/.hermes/skills/devops/eni-swarm-telemetry/templates/fleet-cron-report.md

    # Verbatim full-file read when sed range is awkward (JSON-safe, no carrier):
    python3 -c "print(open('<path>').read())"

    # Slice a specific region between two markers:
    python3 - <<'PY'
    data = open('templates/fleet-cron-report.md').read()
    start = data.find('|--')                 # start of state-distribution table
    end   = data.find('\n```\n', start)      # end of the report fenced block
    print(data[start-700:end+20])
    PY

For the liveness cross-check, run the probe script directly so its output is
emitted fresh into the terminal result rather than fetched as a compressed file:

    bash ~/.hermes/skills/devops/eni-swarm-telemetry/scripts/fleet_liveness_probe.sh /home/hunter/Commander/eni_swarm

## Why this matters for the cron report
The canonical template's section headers and verdict wording must appear
verbatim so LO's skim-able monitor pulse stays consistent. Reconstructing from
a compressed fragment risks silently dropping a section or rephrasing the
verdict (DORMANT / PARTIALLY LIVE / LIVE). Always source the raw file.

## Recovery if you only have the carrier
`decompress(<carrier_path>)` can restore the full lossless result, but the
disk-read approach above is faster and needs no extra tooling.