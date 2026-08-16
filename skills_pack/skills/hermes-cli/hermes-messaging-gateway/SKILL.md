---
name: hermes-messaging-gateway
description: Connect a messaging platform backend (Signal, and similar daemon-backed channels) to the Hermes agent gateway so LO can talk to the agent from his phone. Covers the universal step of matching the platform daemon's served HTTP endpoints to what the Hermes platform adapter expects, the link-as-secondary/QR workflow for already-registered accounts, keeping the daemon alive via systemd/container restart, the env vars the gateway reads (SIGNAL_*, WHATSAPP_*, etc.), AND the model-resolution trap (gateway resolves model.default BEFORE model.model, so a stale default silently overrides the chat model for messaging conversations). Use whenever the user says "use you through <app>", "set me up on Signal/WhatsApp/Telegram", "add a messaging channel", "use <model> for the <channel> chat", a phone-side "network error" appears during device linking, or a messaging reply uses the wrong model.
version: 1.0
author: ENI
tags: [hermes, gateway, messaging, signal, whatsapp, channels, integration, qr]
related_skills: [local-llm-finetuning]
---

# Hermes Messaging Gateway integration

Hermes ships a gateway with per-platform adapters. The CLI help lists them
(`hermes gateway` / subcommands); the platform registry lives in
`hermes_cli/platforms.py` (`PLATFORMS` OrderedDict — each entry's `key` maps to
a `hermes-<key>` toolset), and the actual send/receive adapter code lives in the
**separate `gateway` package** at `site-packages/gateway/platforms/<platform>.py`,
NOT in `hermes_cli`. `hermes_cli/gateway.py` only does the interactive setup
prompts + env-var writes.

## Cardinal rule: match the DAEMON's dialect to the ADAPTER's endpoints

The #1 time-sink and failure mode. Each platform needs a backend daemon, but the
daemon's HTTP API surface and the Hermes adapter's expected surface are usually
from DIFFERENT projects and often differ:

- Signal: Hermes adapter (`gateway/platforms/signal.py`) calls
  `/api/v1/check`, `/api/v1/events?account=...` (SSE stream), `/api/v1/rpc`
  (JSON-RPC) — this is the **native signal-cli** HTTP-daemon dialect.
- The popular Docker image `bbernhard/signal-cli-rest-api` serves a DIFFERENT
  dialect (`/v1/register/{num}`, `/v1/send`, `/v1/qrcodelink`, `/v1/receive`)
  — it 404s on every `/api/v1/*` path Hermes expects. Do NOT waste time bridging
  it; run native signal-cli instead.

**Process to follow every time:**
1. Open `site-packages/gateway/platforms/<platform>.py` and grep the endpoint
   paths the adapter builds (`http_url` + `/api/...` or `/v1/...`).
2. Start the backend daemon and `curl` those EXACT paths. If they 404 while the
   daemon is healthy, the backend is the wrong dialect — swap it, don't patch a
   bridge.
3. Only after paths respond, wire the env vars and enable the channel.

## Signal end-to-end (link an already-registered number as a secondary device)

Hermes env keys it reads: `SIGNAL_HTTP_URL`, `SIGNAL_ACCOUNT`, `SIGNAL_ALLOWED_USERS`,
`SIGNAL_GROUP_ALLOWED_USERS`.

Native signal-cli 0.14.x (latest) — install WITHOUT sudo from a home dir:
- Download the **`Linux-native`** build tarball (single 372M `signal-cli` binary,
  bundles libsignal — the plain `.tar.gz` needs a Gradle build for native libs).
- `tar xzf ... ` into `~/signal-cli/`, run `./signal-cli --version`.
- It compiles its service endpoint as **`grpc.chat.signal.org`** (NOT the legacy
  `textsecure-service.whispersystems.org`, whose DNS is now dead). If a phone
  scan reports "network error", confirm the box reaches `grpc.chat.signal.org`
  (`curl -sI https://grpc.chat.signal.org` → TLS handshake OK). Machine
  connectivity is usually fine; the error is stale/expired link state.

Link-as-secondary (account already on the phone's Signal app):
- `signal-cli link -n "HermesAgent"` — do NOT pass an account/phone number when
  linking (`You cannot specify a account (phone number) when linking`).
- The URI is printed to stdout; signal-cli does NOT draw the QR itself. Render it:
  `pip install qrcode[pil]` into a venv (system python is PEP-668-blocked), then
  produce a PNG and/or a terminal ASCII of solid blocks (chr 9608).
- CRITICAL: the link process must stay ALIVE while the user scans (the QR is a
  single session and expires). Launch with `setsid ./signal-cli link ... &
  </dev/null > /tmp/link_uri.txt` and verify `pgrep -f 'signal-cli link'` is
  alive BEFORE rendering the QR. Render the QR from the CURRENT uri in
  `/tmp/link_uri.txt`, not a stale one.
- User scans via Signal app → Settings/profile → **Linked devices** → **Link new
  device**. If the terminal block-chars are hard to scan, point them at the PNG.
- If it expires/times out: regenerate a fresh live link, don't reuse the old URI.

## Keeping the daemon alive
Run it under systemd user service (`Restart=on-failure` + `loginctl enable-linger
<user>`) or a container with `--restart unless-stopped`, so a reboot/wifi-drop
doesn't silently kill the channel (same philosophy as
`local-llm-finetuning`'s resume watchdog).

## ⚠️ Model-resolution trap (messages use the WRONG model)
The gateway resolves the chat model in `run.py::_resolve_gateway_model`:
```python
return model_cfg.get("default") or model_cfg.get("model") or ""
```
It reads **`model.default` FIRST**, falling back to `model.model`. This is the
opposite of the intuition from `config.yaml` (where `model.model` is the "active"
model and `model.default` a fallback). If `model.default` points at a stale model
(e.g. a `:free` catch-all) while `model.model` holds the model you actually chose,
**every messaging/Signal conversation silently uses the stale default.** Symptom:
you set `model.model` to e.g. deepseek-v4-0731 but the gateway still answers from
the old default.

Fix: set BOTH keys to the intended model:
```bash
hermes config set model.default deepseek/deepseek-v4-flash-0731
hermes config set model.model   deepseek/deepseek-v4-flash-0731
hermes gateway restart
```
Confirm what a fresh gateway resolves:
```bash
cd ~ && python3 -c "
import os; os.environ['HERMES_HOME']='/home/hunter/.hermes'
from hermes_cli.env_loader import load_hermes_dotenv; load_hermes_dotenv()
from gateway.run import _resolve_gateway_model
print('gateway resolves ->', _resolve_gateway_model())
"
```

## Gateway install/restart quirks (systemd user service)
- `hermes gateway install` prompts twice ("start now?" then "start on boot?").
  Non-interactive: `printf 'y\ny\n' | hermes gateway install`.
- `hermes gateway restart` can HANG (foreground timeout). Fall back to
  `systemctl --user restart hermes-gateway.service` and verify the SSE stream
  came back: `ss -tnp | grep 8080` should show an ESTAB from the gateway `python3`.
- The gateway reads `~/.hermes/.env` ONCE at startup. Any env/config change needs
  a gateway restart to take effect — a running gateway never re-reads env vars.
- To confirm a platform is enabled without restarting the gateway, run the
  `load_gateway_config()` probe (see signal-setup.md).

## Support files
- `references/signal-setup.md` — full Signal setup transcript incl. exact
  commands, env vars, and the daemon-vs-container dialect failure.
