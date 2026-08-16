---
name: hermes-signal-integration
description: >-
  Connect Hermes to the Signal messenger as a chat platform (think Telegram/Discord/WhatsApp).
  Covers the NON-OBVIOUS backend requirement — Hermes' Signal adapter speaks native
  signal-cli HTTP-daemon JSON-RPC (/api/v1/check, /api/v1/events SSE, /api/v1/rpc) and is NOT
  compatible with the popular bbernhard/signal-cli-rest-api Docker REST wrapper (/v1/* dialect).
  Includes linking a Signal number as a secondary device via QR, rendering scan-able QRs in a
  terminal, the required env vars (SIGNAL_HTTP_URL, SIGNAL_ACCOUNT, SIGNAL_ALLOWED_USERS), and
  enabling the platform in the gateway. Use whenever the user says "set up Signal", "use you
  through Signal / via Signal", or wants a new local messaging channel for Hermes.
version: 1.0
author: llyra
tags: [hermes, signal, chat, gateway, messaging, integration]
related_skills: []
---

# Hermes ↔ Signal Integration

Hermes ships Signal as a first-class platform (`📡 Signal`, toolset `hermes-signal`,
plus every other chat platform: telegram, discord, slack, whatsapp, matrix, mattermost… —
see `hermes_cli/platforms.py` PLATFORMS registry). Getting it to work hinges on running
**the right backend**, because the adapter is picky.

## The #1 trap: which signal backend to run

Hermes' Signal adapter (`gateway/platforms/signal.py`) is written for the **native
signal-cli HTTP daemon** over JSON-RPC:

- `GET  {SIGNAL_HTTP_URL}/api/v1/check`          (health)
- `GET  {SIGNAL_HTTP_URL}/api/v1/events?account=…`  (inbound, Server-Sent Events stream)
- `POST {SIGNAL_HTTP_URL}/api/v1/rpc`            (JSON-RPC 2.0, outbound/actions)

**The `bbernhard/signal-cli-rest-api:latest` Docker image does NOT speak this dialect.**
It exposes a wrapper REST API (`/v1/register/{n}`, `/v1/qrcodelink`, `/v1/send`, `/v1/receive`,
`/v1/health`, ...). Pointing Hermes at it — even with the number linked — returns 404 on every
`/api/v1/*` call. Symptom: container healthy, `signal-cli` connects to daemon, but every
endpoint Hermes calls 404s. DO NOT build a bridge; run native signal-cli instead.

> Verify quickly: `strings <rest-binary>` or just `curl <url>/api/v1/check` — if 404 and the
> image offers `/v1/register`, it's the wrong dialect.

## Backend: native signal-cli HTTP daemon (no sudo needed)

The correct backend is the official `signal-cli` binary in **HTTP daemon mode**.

- Latest native release: `AsamK/signal-cli` → assets → `signal-cli-VERSION-Linux-native.tar.gz`
  (bundles libsignal — **much** easier than the plain `.tar.gz` which needs Gradle-built libs).
- The native build extracts to a **single self-contained 372MB `signal-cli` binary** — no
  `bin/` subdir (the `.tar.gz` variant has `bin/signal-cli`; the native one is the binary itself).
- Install by extracting under the user's home (e.g. `~/signal-cli/`) — **avoids /opt + sudo**,
  which many users will rightly refuse for a messaging daemon.
- Needs a JRE at runtime (openjdk works).
- Run as a daemon: `./signal-cli -a +1NNN... daemon --http 127.0.0.1:8080`
  (exit 0 immediately; keep it alive under systemd user service with linger so it survives reboot).

## Account must be linked as a SECONDARY device

signal-cli can't mint a fresh bot number — Signal requires either (a) registering a new number
via SMS code, or (b) **linking an already-running number as a secondary device via QR**. If the
user's number is already in Signal on their phone, use the QR link (you/they scan from the phone
app; your PC becomes another device seeing the same messages).

Link command — note the syntax quirks:
- `./signal-cli link -n "HermesAgent"`  → prints `sgnl://linkdevice?uuid=…&pub_key=…`
- **Do NOT pass `--account` to link** — errors with "You cannot specify a account (phone number)
  when linking". In some versions `--account` isn't recognized at all by `link`.
- The link is single-session and **expires in ~a couple minutes**. The `link` process must stay
  ALIVE while the user scans. Run it backgrounded, capture stdout to a file, then render the QR
  from the CURRENT uri — never re-render an old uri from a process that already exited.

User-side step: phone Signal app → Settings/avatar → **Linked devices** → **Link new device** →
point camera at the QR.

## Rendering a scan-able QR from a terminal (no sudo, PEP-668-safe)

```bash
python3 -m venv /tmp/qrvenv && /tmp/qrvenv/bin/pip install qrcode[pil]
/tmp/qrvenv/bin/python - <<'PY'
import qrcode,sys
uri=open('/tmp/sg_link_uri.txt').read().strip()
qr=qrcode.QRCode(border=2); qr.add_data(uri); qr.make()
[print(''.join(chr(9608)*2 if c else '  ' for c in r)) for r in qr.get_matrix()]
PY
```
- System python is PEP-668 locked → always pip into a venv (or an existing venv like
  `~/.venvs/eni-train`), never `--break-system-packages` into the system interpreter.
- The block-char ASCII QR (`chr(9608)` double-width) scans fine from a dark terminal.
- Also save a high-res PNG (`border=4, box_size=10`) to a path you give the user.
- If it expires: just rerun `link` in background, re-read uri, re-render — tell the user.

## Env + gateway wiring

Env vars the gateway reads (name-checked in `hermes_cli/gateway.py` and `gateway/platforms/signal.py`):
- `SIGNAL_HTTP_URL`   → `http://127.0.0.1:8080`
- `SIGNAL_ACCOUNT`    → the linked E.164 number, e.g. `+17808932704`
- `SIGNAL_ALLOWED_USERS` → comma-separated numbers allowed to DM the bot
- `SIGNAL_GROUP_ALLOWED_USERS` (optional, for group access)
- `SIGNAL_ACCOUNT` is the **account number used as the url query param `?account=`** — must match
  exactly the linked number.

Status check: `hermes status` reports signal as "configured" once both `SIGNAL_HTTP_URL` and
`SIGNAL_ACCOUNT` are set. Use `hermes gateway` / `hermes setup` (Signal) to take the interactive
path, or set the env vars manually then enable the platform in the gateway config.

## Pitfalls summary
- bbernhard Docker REST wrapper ≠ native signal-cli; Hermes needs native (`/api/v1/*`).
- Link without `--account`; keep the link process alive; render the CURRENT uri.
- Native single-binary layout (no bin/); JRE required; run daemon under systemd user + linger.
- pip: always venv, PEP-668 blocks system-site.
- Confirm daemon reachable with `curl <url>/api/v1/check` before linking.

See `references/signal-setup-session.md` for the live transcript/decisions.
