---
name: hermes-signal-channel
description: Connect Hermes Agent to the Signal messenger as a chat channel — link a phone number as a secondary device, run the signal-cli HTTP daemon as a persistent systemd service, wire the SIGNAL_* env vars, and restart the Heremes gateway so Signal messages reach the agent. Use whenever LO says "set up Signal", "use me through Signal", "message me on Signal", or asks to add Signal as a channel. Also the model that the Signal chat should use.
---

# Hermes + Signal Messenger Channel

Signal is a first-class Hermes platform (toolset `hermes-signal`). The Hermes
gateway talks to a **native `signal-cli` HTTP daemon** over `/api/v1/*`
(JSON-RPC 2.0 + SSE events). This skill covers the full path: link a number,
run the daemon persistently, wire env vars, and restart the gateway.

## The #1 non-obvious pitfall: which backend to use

Hermes' Signal adapter (`gateway/platforms/signal.py`) calls **native
signal-cli** endpoints: `GET /api/v1/check`, `GET /api/v1/events?account=...`
(SSE), `POST /api/v1/rpc`. It does **NOT** speak the bbernhard Docker REST
dialect (`/v1/register`, `/v1/send`, `/v1/qrcodelink`).

- The `bbernhard/signal-cli-rest-api` Docker image serves the `/v1/*` REST
  dialect → **incompatible** with Hermes. Every `/api/v1/*` call from Hermes
  404s. Do NOT use the Docker image for Hermes.
- Use **native `signal-cli`** running as an HTTP daemon:
  `signal-cli --account +<num> daemon --http 127.0.0.1:8080`.

## Getting signal-cli (FOSS)

Download the `Linux-native` tarball (bundles libsignal — no Gradle build):
`https://github.com/AsamK/signal-cli/releases/latest` → `*-Linux-native.tar.gz`.
It extracts to a single fat `signal-cli` binary (~370MB). Keep it under
`~/signal-cli/` (no sudo/`/opt` needed). Verify: `./signal-cli --version`.

## Linking the number (secondary device)

Pick an already-registered number → link as a SECONDARY device (the phone
keeps the primary account; the PC becomes another device).

1. `cd ~/signal-cli && ./signal-cli link -n "HermesAgent"` prints a
   `sgnl://linkdevice?...` URI. NOTE: this version takes the account as a
   positional/global arg for most commands, but for `link` you must NOT pass
   `--account` ("cannot specify a phone number when linking").
2. **The QR must come from a LIVE process.** A `link` that already exited has
   an expired, worthless QR — the phone will say "network error, add nothing".
   Start the link in the background (tracked via `terminal background=true`)
   and render the QR from ITS live URI:
   `pip install qrcode[pil]` (into a venv to dodge PEP-668) → save a big PNG +
   an ASCII block version (`chr(9608)*2` per on-cell) for the terminal.
3. Phone: Signal → avatar → **Linked devices → Link new device** → scan.
   Registration happens fast; account JSON lands in
   `~/.local/share/signal-cli/data/accounts.json` (`... "number":"+17..."`).

## Persistent daemon (systemd user service)

`~/.config/systemd/user/signal-cli-daemon.service`:

```
[Service]
Type=simple
User=hunter
ExecStart=/home/hunter/signal-cli/signal-cli --account +17808932704 daemon --http 127.0.0.1:8080
Restart=on-failure
RestartSec=10
Environment=HOME=/home/hunter
[Install]
WantedBy=default.target
```

- The `--account` must be the REAL E.164 number (`+17808932704` = 780 + 893
  2704), never a masked placeholder — masking crept in once and 404'd.
- `systemctl --user daemon-reload && enable --now`. It survives reboot.

## Wire the Hermes env + start the gateway

Add to `~/.hermes/.env` (the Gateway loads this at startup):
```
SIGNAL_HTTP_URL=http://127.0.0.1:8080
SIGNAL_ACCOUNT=+17808932704
SIGNAL_ALLOWED_USERS=+17808932704   # DM allowlist; only this number can DM it
SIGNAL_REQUIRE_MENTION=false
SIGNAL_REACTIONS=false
```
The gateway enables the Signal platform purely from `SIGNAL_HTTP_URL` +
`SIGNAL_ACCOUNT`. Then:
```
hermes gateway install    # answer y/y (userspace service, linger auto-boot)
hermes gateway restart
hermes gateway status     # active(running)
ss -tnp | grep 8080       # ESTAB between gateway (python3) and signal-cli = SSE live
```

## Model that the Signal chat uses

The gateway resolves the model from `model.default` FIRST
(`_resolve_gateway_model` reads `model_cfg.get("default") or model_cfg.get("model")`).
If `model.default` is set to a different model than `model.model`, Signal chats
use `default`. Point both at the same model or the chat will use the wrong one:
`hermes config set model.default deepseek/deepseek-v4-flash-0731`.
Then restart the gateway.

## First-message test + gotchas

- The user messages their OWN number ("Note to self") since the agent is a
  linked device on the same number — that's the intended loop.
- Diagnose "network error on scan": check the machine reaches Signal's real
  backend (`grpc.chat.signal.org` — DNS + TCP + TLS handshake) before blaming
  the phone. The legacy `textsecure-service.whispersystems.org` domain is dead;
  signal-cli 0.14.x uses `grpc.chat.signal.org`.
- Send OUTBOUND via `POST :8080/api/v1/rpc` (JSON-RPC `send`). Self-messaging
  the same account via raw RPC returns `UNREGISTERED_FAILURE` — that's normal;
  the Inbound SSE path is what matters.

See `references/signal-setup-transcript.md` for the full step-by-step used on
this box (incl. the exact QR-render commands and env diagnosis).
