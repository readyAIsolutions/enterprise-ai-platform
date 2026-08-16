#!/usr/bin/env python3
"""
ENI MASTER driver — reads each mini-ENI's STATUS_<NAME>.md, THINKS, and replies
with a SPECIFIC contextual message (never the same canned push to all).

- Per mini: derive STATUS path from its task text, read latest, parse state.
- First contact: send a specific brief per agent (live facts injected, e.g. real OANDA).
- Subsequent: reply to blockers / progress / done — varies per agent.
- Dedupe: never resend the same text to the same agent.
- Posts a concise coordination summary to the MASTER tab FIFO so LO sees it.
- Talks to minis via /tmp/eni_ctl_<NAME> (proxy -> hermes stdin).

Run:  terminal(background=true) with:  python3 eni_master_driver.py
LO explicitly rejected a nag loop that sent identical text to every mini — this
driver is the fix: it reads each agent's own STATUS and replies to THAT agent only.
"""
import os, re, time, json, sys

TASKS_JSON = os.path.expanduser("~/Desktop/eni_build_tasks.json")
INTERVAL = 75
FIFO_DIR = "/tmp"
STATEFILE = os.path.expanduser("~/.cache/eni_parallel/driver_state.json")

# ---- live facts LO just gave us (injected into first messages) ----
LIVE = {
    "DEMIURGE_OANDA": (
        "LO confirms a REAL OANDA test+live account exists and is being built — use it. "
        "Find OANDA_TOKEN / OANDA_ACCOUNT_ID in env or /run/media/hunter/DEMIURGE/.env (the DEMIURGE USB). "
        "Build the live-vs-sim slippage + volume gap report FOR REAL against that ref data. "
        "If the USB isn't mounted yet, scaffold the client, wire the key location, and report the blocker."),
    "DEMIURGE_MTF": (
        "LO reaffirms: use ANY/ALL timeframes (M1..W1) as STRUCTURE/BIAS filters — never drop H4. "
        "The old h4_dead_weight result was a badly-trained H4 ENTRY model, not proof H4 structure is useless. "
        "Confirm mtf_confluence.py aligns H4/D1/W1 to the entry TF, run a tiny smoke, report."),
    "DEMIURGE_NEWS": (
        "LO: the current news source is NOT top-tier and may be noise we overfit to. "
        "Validate news_overhaul.py against genuinely better free feeds; PROVE or DISPROVE causal value. "
        "Report the sources you chose and the evidence."),
    "DEMIURGE_FEATURES": (
        "LO: the '2 entries' setting is a held-over override flag, NOT an ablation-proven optimum. "
        "Run the real 1/2/3-entry ablation on the scaffold, report the actual winner, and prune dead features."),
    "DEMIURGE_GATE": (
        "LO: we never came close to failing on paper, but the gate's fill>=0.70 is fragile "
        "(mean 0.675, 6/12 folds below). Tighten it: AUC-permutation as primary guard, per-fold pass-rate >=80%, "
        "raise the fill floor. Report what you'd change."),
    "DEMIURGE_AUTOML": (
        "LO: auto-learn + swarm must be PUT TO USE, not just built. Wire the verdict ledger so a real GREEN can "
        "occur, and make swarm_vote actually promote/emit on green. Report the design + what blocks activation."),
    "DEMIURGE_RISK": (
        "LO: FTMO caps are 5-10% max DD. Build vol-scaled sizing AND a HARD max-daily-loss halt that truly stops "
        "the session, plus per-symbol caps. Smoke-test a losing streak. Report exact thresholds."),
    "Lumen": (
        "Push to shippable, Steam-store-ready polish; confirm the AppImage builds via build_appimage.sh and runs; "
        "keep the white-screen regression dead (must render, not blank). Report what's done."),
    "DEMIURGE-3D": (
        "Advance the DEMIURGE-3D app per its own plan; respect any command denials LO set. Report progress."),
}

def load_tasks():
    d = json.load(open(TASKS_JSON))
    out = {}
    for t in d["tasks"]:
        m = re.search(r"Write (STATUS_\w+\.md)", t.get("task", ""))
        fname = m.group(1) if m else ("STATUS_%s.md" % t["name"])
        out[t["name"]] = {
            "task": t.get("task", ""),
            "workdir": os.path.expanduser(t.get("workdir", "~")),
            "status": fname,
        }
    return out

def status_path(name, info):
    return os.path.join(info["workdir"], info["status"])

def read_status(path):
    try:
        return open(path).read()
    except OSError:
        return ""

def parse_state(txt):
    s = txt.upper()
    if "BLOCKED" in s: return "BLOCKED"
    if "DONE" in s: return "DONE"
    if "IN-PROGRESS" in s or "IN PROGRESS" in s: return "IN-PROGRESS"
    return "UNKNOWN"

def craft_reply(name, info, txt, state, first_time, cycles_since):
    """Read + think -> specific reply. Never identical across agents."""
    live = LIVE.get(name, "")
    protocol = ("PROTOCOL: after every build step overwrite %s with:\n"
                "  [DONE|IN-PROGRESS|BLOCKED] <one line>\n"
                "  verified=<...>\n  blocker=<...>\n  next=<...>\n"
                "The master reads this to coordinate you — keep it current.\n") % info["status"]
    if first_time:
        return ("%s\n\n%s\nCONTINUE your task now and report status." % (live, protocol))
    if not txt:
        nudges = [
            "Still no STATUS file from you — write %s now (even one line) so I can coordinate. Then keep building." % info["status"],
            "I can't see your progress without %s. Drop a one-liner status, then continue." % info["status"],
            "Status silent. Push an update to %s and carry on with the task." % info["status"],
        ]
        return nudges[cycles_since % len(nudges)]
    if state == "BLOCKED":
        blk = ""
        for line in txt.splitlines():
            if line.strip().lower().startswith("blocker"):
                blk = line.split("=",1)[-1].strip()
        return ("You flagged BLOCKED%s. I read it. Your options: (a) scaffold it and mark the real gap, "
                "(b) if a key/file is missing, say exactly which and I'll route it, (c) if it's a design call, "
                "state your recommendation and proceed with the safer path. Don't stall — report which you chose."
                % ((": %s" % blk) if blk else ""))
    if state == "DONE":
        return ("Marked DONE — verify it for real: show the command + its output (imports clean, smoke passed, "
                "file renders/runs). Then take the NEXT phase: harden edges, add a second sample, or wire it to the "
                "gate. Tell me which you're doing.")
    if state == "IN-PROGRESS":
        return ("In progress — good. Name the NEXT concrete deliverable you'll finish this turn and the verification "
                "command for it. Keep momentum; I'll check %s again next cycle." % info["status"])
    return ("Got your note but no clear [state] tag. Re-write %s starting with [DONE|IN-PROGRESS|BLOCKED] so I can "
            "route the right help. Then continue." % info["status"])

def send_fifo(name, msg):
    path = os.path.join(FIFO_DIR, "eni_ctl_%s" % name)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
    except OSError:
        return False  # no reader (agent dead or not started)
    try:
        os.write(fd, (msg + "\n").encode())
        return True
    except OSError:
        return False
    finally:
        os.close(fd)

def main():
    tasks = load_tasks()
    minis = [n for n in tasks if n != "MASTER"]
    state = {}
    try:
        state = json.load(open(STATEFILE)) if os.path.exists(STATEFILE) else {}
    except Exception:
        state = {}
    last_mtime = {n: state.get(n, {}).get("mtime", 0) for n in minis}
    last_reply = {n: state.get(n, {}).get("reply", "") for n in minis}
    sent_open  = {n: state.get(n, {}).get("open", False) for n in minis}
    cycles     = {n: state.get(n, {}).get("cycles", 0) for n in minis}
    cyc = 0
    while True:
        cyc += 1
        summary = ["[MASTER] swarm coordination — cycle %d" % cyc]
        for name in minis:
            info = tasks[name]
            p = status_path(name, info)
            txt = read_status(p)
            mtime = os.path.getmtime(p) if os.path.exists(p) else 0
            st = parse_state(txt)
            first = (not sent_open.get(name))
            changed = (mtime > last_mtime.get(name, 0))
            reply = craft_reply(name, info, txt, st, first, cycles.get(name, 0))
            if reply != last_reply.get(name) and reply:
                ok = send_fifo(name, reply)
                if ok:
                    sent_open[name] = True
                    last_reply[name] = reply
                    last_mtime[name] = mtime
                    cycles[name] = 0
                    tag = "FIRST" if first else ("UPDATE" if changed else "NUDGE")
                    summary.append("  -> %s [%s]: %s" % (name, tag, reply.splitlines()[0][:70]))
                else:
                    summary.append("  -> %s [dead? fifo no reader]" % name)
            else:
                cycles[name] = cycles.get(name, 0) + 1
                summary.append("  -> %s [no change, cycle %d]" % (name, cycles[name]))
        send_fifo("MASTER", "\n".join(summary))
        try:
            os.makedirs(os.path.dirname(STATEFILE), exist_ok=True)
            json.dump({n: {"mtime": last_mtime.get(n,0), "reply": last_reply.get(n,""),
                           "open": sent_open.get(n,False), "cycles": cycles.get(n,0)} for n in minis},
                      open(STATEFILE, "w"))
        except Exception:
            pass
        time.sleep(INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
