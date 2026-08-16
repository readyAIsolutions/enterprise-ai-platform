# Signal ↔ Hermes setup transcript (this box, 2026-08)

Concrete commands + diagnostics used to link +7808932704 as a secondary
device and wire it as a Hermes channel. Numbers shown masked; substitute the
real E.164.

## Download + verify native signal-cli
```bash
curl -sL https://github.com/AsamK/signal-cli/releases/download/v0.14.7/signal-cli-0.14.7-Linux-native.tar.gz -o /tmp/signal-cli.tar.gz
mkdir -p ~/signal-cli && cd ~/signal-cli && tar xzf /tmp/signal-cli.tar.gz
./signal-cli --version   # signal-cli 0.14.7
```

## Link (live process must stay up)
```bash
cd ~/signal-cli && ./signal-cli link -n "HermesAgent"   # prints sgnl://linkdevice?uuid=...
```
Keep the process ALIVE. Render QR from the live URI (venv to bypass PEP-668):
```bash
/your/venv/bin/pip install qrcode[pil]
cat > /tmp/mkqr.py <<'EOF'
import qrcode
qr = qrcode.QRCode(border=4, box_size=12)
qr.add_data(open('/tmp/sg_link_uri.txt').read().strip())
qr.make()
qr.make_image(fill='black', back_color='white').save('/home/hunter/signal-cli/signal_link_qr.png')
print('saved')
EOF
/your/venv/bin/python /tmp/mkqr.py
xdg-open /home/hunter/signal-cli/signal_link_qr.png    # opens live QR in viewer
```
Terminal ASCII alt (previous `link` URI only used for display):
```
/your/venv/bin/python -c "import qrcode,sys; qr=qrcode.QRCode(border=2); qr.add_data(open('/tmp/sg_link_uri.txt').read().strip()); qr.make(); [sys.stdout.write(''.join(chr(9608)*2 if c else '  ' for c in r)+'\n') for r in qr.get_matrix()]"
```
POINT: a previously-exited `link` yields a dead QR → "network error, add
nothing" on the phone. Always render from a fresh, running process.

## Daemon service
`~/.config/systemd/user/signal-cli-daemon.service` (ExecStart runs the native
daemon on 127.0.0.1:8080). Enable+start. Verify:
```
ss -tlnp | grep 8080            # LISTEN [::ffff:127.0.0.1]:8080 signal-cli
journalctl --user -u signal-cli-daemon | grep -E 'sync|Envelope'   # receiving
```

## Backend reachability diagnosis (before blaming the phone)
```bash
nslookup grpc.chat.signal.org 8.8.8.8          # DNS OK (15.197.x)
curl -sv https://grpc.chat.signal.org/         # TLS 1.3 handshake completes
```
The legacy `textsecure-service.whispersystems.org` does NOT resolve (dead).
signal-cli's real service is `grpc.chat.signal.org`.

## Env + gateway
Append SIGNAL_* to `~/.hermes/.env` (see SKILL.md). Then:
```
printf 'y\ny\n' | hermes gateway install
hermes gateway restart
hermes gateway status      # active (running)
ss -tnp | grep 8080        # ESTAB python3 <-> signal-cli = SSE stream live
```

## Outbound note
`POST :8080/api/v1/rpc {"method":"send", ...}` — self-messaging same account
returns `UNREGISTERED_FAILURE`; that is expected and not a daemon fault. The
agent receives via the SSE stream, which is the path that matters.

## Model trap
`model.default` wins over `model.model` for messaging chats. Set both:
`hermes config set model.default deepseek/deepseek-v4-flash-0731`.
