# Signal → Hermes live setup session (2026-08-07)

Transcript of decisions made while wiring this box to Signal. Numbers/URIs are from the live
session; treat as example, not current state.

## Decision 1: backend route chosen
- Offered two paths: Docker `bbernhard/signal-cli-rest-api` vs native signal-cli.
- User chose **1 (Docker)** initially, then the bbernhard image proved incompatible (see below).
- Actually executed: **native signal-cli** in home dir, no sudo.

## The incompatibility, concrete
- Pulled `bbernhard/signal-cli-rest-api:latest`, ran:
  `docker run -d --name signal-cli --restart unless-stopped -e MODE=json-rpc \
   -v ~/.signal-cli/data:/home/.local/share/signal-cli -p 8080:8080 bbernhard/...`
- Every Hermes endpoint 404'd:
  - `POST /api/v1/check` → 404
  - `GET /api/v1/events?account=+1` → 404
  - `POST /api/v1/rpc` → 404
- `strings <rest-binary>` showed `/v1/health`, `/v1/register/{number}`, `/v1/qrcodelink`,
  `/v1/receive/{number}`, `/v1/send` → confirmed the /v1/* dialect. Wrong backend.
- Stopped+removed the container (`docker stop signal-cli && docker rm signal-cli`).

## Native install that worked
- Downloaded `signal-cli-0.14.7-Linux-native.tar.gz` from AsamK/signal-cli releases (~105MB).
- Extracted to `~/signal-cli/` — came out as ONE file `./signal-cli` (372MB self-contained,
  no bin/ dir). Verify: `./signal-cli --version` → `signal-cli 0.14.7`.
- openjdk 25 present.

## Link session
- First attempt `./signal-cli link --account "+1..." -n "HermesAgent"` →
  `error: unrecognized arguments: '--account'` (link has no --account arg in 0.14.x).
- `./signal-cli -a +1... link -n "HermesAgent"` → `You cannot specify a account when linking`.
- Correct: `./signal-cli link -n "HermesAgent"` → prints
  `sgnl://linkdevice?uuid=…&pub_key=…`.
- Ran backgrounded to keep it alive: `(./signal-cli link -n "HermesAgent" > /tmp/sg_link_uri.txt 2>&1 &)`
  then `pgrep -f 'signal-cli link'` to confirm alive while user scans.

## QR rendering
- `pip install qrcode` blocked: PEP-668 (externally-managed-environment).
- Installed into the existing venv:
  `/home/hunter/.venvs/eni-train/bin/pip install qrcode[pil]`
- Rendered ASCII QR (chr(9608) double-width, border=2) from current uri + high-res PNG
  (`qrcode.QRCode(border=4, box_size=10)` → `~/signal-cli/signal_link_qr.png`).
- Rule learned: NEVER render the uri from a link process that already exited — regenerate.

## Next steps if resumed
- After QR scan: `/api/v1/check` (native) should report the daemon healthy.
- Set env: `SIGNAL_HTTP_URL=http://127.0.0.1:8080`, `SIGNAL_ACCOUNT=+178...` (linked number),
  `SIGNAL_ALLOWED_USERS=<user's number(s)>`.
- Run the native daemon as a systemd **user** service with linger so it survives reboot
  (same pattern as eni-train.service): `systemctl --user enable ...; loginctl enable-linger`.
- Enable signal platform in gateway config → test send/receive.
