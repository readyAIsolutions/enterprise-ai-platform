# Signal link QR — the live-process reproduction recipe

The phone reading "network error" / "add nothing" is almost always a QR rendered
from a **dead or lapsed `signal-cli link` process**. Signal link codes are
single-session and expire in seconds. Render ONLY from a live process.

## Correct sequence (worked end-to-end on 2026-08)

1. Start link as a tracked background process so it stays alive:
```bash
cd ~/signal-cli
rm -f /tmp/sg_link_uri.txt
./signal-cli link -n "HermesAgent" 2>&1 | tee /tmp/sg_link_uri.txt   # background=true
```
2. Wait ~4s; confirm the URI exists AND the process is still alive:
```bash
cat /tmp/sg_link_uri.txt        # -> sgnl://linkdevice?uuid=...&pub_key=...
pgrep -f 'signal-cli link' && echo ALIVE_AND_WAITING
```
3. Render **that exact live URI** as a QR. The qrcode lib is not on the system
   python (PEP-668) — use the project venv:
```bash
/home/<user>/.venvs/eni-train/bin/pip install qrcode[pil] -q
/home/<user>/.venvs/eni-train/bin/python - <<'PY'
import qrcode
uri = open('/tmp/sg_link_uri.txt').read().strip()
qr = qrcode.QRCode(border=4, box_size=12); qr.add_data(uri); qr.make()
qr.make_image(fill='black', back_color='white').save('/home/<user>/signal-cli/signal_link_qr.png')
PY
```
   Avoid shell-quoting hell on the `&` and `%` in the URI — write a small .py
   file and run it, or pass the URI via a file read, never inline with quotes.
4. Open the PNG for the user (or print an ASCII QR in the terminal):
```bash
xdg-open /home/<user>/signal-cli/signal_link_qr.png
```
5. User scans on phone (Settings → Linked devices → Link new device).
6. Success looks like: `Received link information from +1... , linking in progress ...` then `Associated with: +1...`. The account dir appears under the data dir.

## The two mistakes that produced "network error"

- Rendered the PNG from a link process that had **already exited** (its URI was
  stale). Re-ran link, re-rendered from the NEW live URI → worked.
- Rendered an ASCII QR but the PNG on disk was still the **stale** one from the
  earlier dead process — user opened the FILE and scanned the dead code.
  Fix: regenerate the PNG from the CURRENT live URI and re-open it.

## Env/timing notes

- A triggered but never-scanned link eventually prints
  `Link request timed out, please try again.` — that process is dead; start fresh.
- Keep `pkill -f 'signal-cli link'` usage sparse: it can kill the caller's own
  shell group (SIGTERM propagates). Prefer `systemctl` / tracked background procs.
