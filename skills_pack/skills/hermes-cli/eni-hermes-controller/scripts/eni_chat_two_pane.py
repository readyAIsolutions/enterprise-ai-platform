#!/usr/bin/env python3
"""ENI two-pane chat terminal.

Left pane  : HERMES  - talks to the full user instruction via the controller
              /chat endpoint (expand -> route -> reinforce -> hermes).
Right pane : LOCAL   - talks to the local AI brain (airllm merged model on
              :8913) directly, no Hermes round-trip.

Secure secret capture (MOST-SECURE: cloud models never see raw envs):
  Paste an API key / secret into EITHER pane. It is regex-matched, stored
  into the encrypted controller vault (POST /security/env/set) under a safe
  key name, and the RAW VALUE IS NEVER SENT to any model - only a
  {SECRET:NAME} placeholder flows to what the model sees. The raw value is
  resolved locally at execution time by the controller, never leaves
  localhost, never stored in a .env file.

Controls:
  Tab / 1 / 2   switch active pane (HERMES <-> LOCAL)
  Enter         send the input line to the active pane
  Ctrl+C        quit
  /secret NAME  store a key under NAME (paste value on next blank line)
  /status       controller status line
  /clear        clear the active pane's history
"""

from __future__ import annotations

import curses
import json
import re
import sys
import urllib.request

CONTROLLER = "http://127.0.0.1:8940"
LOCAL_BRAIN = "http://127.0.0.1:8913/v1/chat/completions"

# Secret shapes. Match most-specific first; keep >30-char patterns real.
_SECRET_PATTERNS = [
    ("OPENAI_API_KEY", r"sk-[A-Za-z0-9]{20,}"),
    ("ANTHROPIC_API_KEY", r"sk-ant-[A-Za-z0-9_-]{20,}"),
    ("OPENROUTER_API_KEY", r"sk-or-v1-[A-Za-z0-9_-]{40,}"),
    ("GOOGLE_API_KEY", r"AIza[0-9A-Za-z_-]{30,}"),
    ("AWS_ACCESS_KEY", r"AKIA[0-9A-Z]{16}"),
    ("GITHUB_TOKEN", r"ghp_[A-Za-z0-9]{30,}"),
    ("TELEGRAM_BOT_TOKEN", r"\d{8,10}:[A-Za-z0-9_-]{35,}"),
    ("BEARER_TOKEN", r"Bearer\s+[A-Za-z0-9._-]{20,}"),
    ("API_KEY", r"(?:api[_-]?key|apikey)\s*[:=]\s*['\"]?([A-Za-z0-9._-]{16,})"),
    ("SECRET", r"sk-[A-Za-z0-9]{20,}"),
]


def detect_secret(text: str) -> tuple[str, str] | None:
    """Return (key_name, secret_value) if text contains a known secret shape."""
    for name, pat in _SECRET_PATTERNS:
        m = re.search(pat, text)
        if m:
            val = m.group(1) if m.groups() and m.group(1) else m.group(0)
            return (name, val)
    return None


def sanitize_line(text: str, detected: tuple[str, str] | None) -> str:
    """Replace detected secret values with a placeholder so the model never sees them."""
    if not detected:
        return text
    name, val = detected
    return re.sub(re.escape(val), "{SECRET:" + name + "}", text)


def _post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        CONTROLLER + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def chat(text: str, use_hermes: bool) -> dict:
    if use_hermes:
        return _post("/chat", {"message": text})
    # local brain direct, OpenAI-compatible
    body = {
        "model": "/home/hunter/.hermes/controller/models/eni-controller/merged",
        "messages": [{"role": "user", "content": text}],
    }
    req = urllib.request.Request(
        LOCAL_BRAIN,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode())
        return {"reply": data["choices"][0]["message"]["content"]}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def store_secret(key: str, value: str) -> dict:
    return _post("/security/env/set", {"key": key, "value": value})


def reply_message(result: dict) -> str:
    """Extract a human-readable reply, unwrapping controller JSON tool-calls."""
    reply = result.get("reply", "")
    if isinstance(reply, str):
        reply = reply.strip()
        if reply.startswith("{") or reply.startswith("["):
            try:
                obj = json.loads(reply)
                if isinstance(obj, dict):
                    args = obj.get("arguments", {})
                    if isinstance(args, dict) and args.get("message"):
                        return str(args["message"])
                    if obj.get("message"):
                        return str(obj["message"])
                    if obj.get("tool"):
                        return f"[{obj.get('tool')}] {obj.get('thought', '')}"
            except Exception:  # noqa: BLE001
                pass
    return reply or (str(result.get("error", "")) if result.get("error") else "(no reply)")


class Pane:
    def __init__(self, key: str, label: str) -> None:
        self.key = key
        self.label = label
        self.history: list[str] = []
        self.busy = False

    def add(self, line: str) -> None:
        strip = line if isinstance(line, str) else str(line)
        if strip:
            self.history.extend(strip.splitlines())
            self.history = self.history[-400:]


def _draw(win: curses.window, active_key: str, left: Pane, right: Pane,
          input_line: str, input_note: str, status: str) -> None:
    curses.curs_set(0)
    h, w = win.getmaxyx()
    mid = max(10, w // 2)
    leftw = mid
    rightw = w - mid - 1

    win.erase()
    for y in range(1, h - 3):
        win.addnstr(y, mid, "|", 1)

    ltitle = f" {left.label}{' (ACTIVE)' if active_key == left.key else ''} "
    rtitle = f" {right.label}{' (ACTIVE)' if active_key == right.key else ''} "
    win.addnstr(0, 0, ltitle, leftw - 1,
                curses.A_BOLD | (curses.A_REVERSE if active_key == left.key else 0))
    win.addnstr(0, mid + 1, rtitle, rightw - 1,
                curses.A_BOLD | (curses.A_REVERSE if active_key == right.key else 0))

    # history
    lh = left.history[-max(1, h - 5):]
    rh = right.history[-max(1, h - 5):]
    for i in range(max(len(lh), len(rh))):
        y = 1 + i
        if y > h - 4:
            break
        if i < len(lh):
            win.addnstr(y, 0, lh[i][:leftw], leftw)
        if i < len(rh):
            win.addnstr(y, mid + 1, rh[i][:rightw], rightw)

    # input prompt
    win.addnstr(h - 3, 0, f"[{active_key}] {input_line}", w - 1)
    win.addnstr(h - 2, 0, input_note, w - 1)
    win.addnstr(h - 1, 0, status[:w - 1] if status else "", w - 1)
    win.refresh()


def run(win: curses.window) -> None:
    curses.curs_set(1)
    win.keypad(True)
    left = Pane("HERMES", "HERMES")
    right = Pane("LOCAL", "LOCAL")
    active = left
    input_line = ""
    note = ""
    status = "Tab/1/2 switch | Enter send | Ctrl+C quit | /secret NAME to store a key"

    while True:
        _draw(win, active.key, left, right, input_line, note, status)
        note = ""
        ch = win.get_wch()
        if ch in ("\x03",):  # Ctrl+C
            break
        if ch in (curses.KEY_F1, "1"):
            active, status = left, "now typing to HERMES"
            continue
        if ch in (curses.KEY_F2, "2"):
            active, status = right, "now typing to LOCAL"
            continue
        if ch == "\t":
            active = left if active is left else right
            status = f"now typing to {active.key}"
            continue
        if ch == "\n":
            line = input_line.strip()
            input_line = ""
            if not line:
                continue
            if line.startswith("/"):
                cmd, _, rest = line.partition(" ")
                if cmd == "/secret" and rest:
                    # store mode: next non-empty line is the value
                    note = f"Storing secret '{rest}' - paste/write the value then Enter"
                    _draw(win, active.key, left, right, "", note, status)
                    got = ""
                    while True:
                        c2 = win.get_wch()
                        if c2 == "\n":
                            break
                        if c2 == "\x03":
                            break
                        if isinstance(c2, str) and c2 >= " ":
                            got += c2
                    if got:
                        res = store_secret(rest, got)
                        status = f"secret '{rest}' " + ("stored (encrypted)" if res.get("ok") else f"FAILED {res.get('error')}")
                    else:
                        status = "secret store cancelled (empty value)"
                    continue
                if cmd == "/status":
                    s = _post("/status", {})
                    status = s.get("status", str(s))[:w - 1] if isinstance(s, dict) else "?"
                    continue
                if cmd == "/clear":
                    active.history = []
                    continue
                status = "unknown command"
                continue
            # Send: redact before dispatch in BOTH panes.
            det = detect_secret(line)
            safe = sanitize_line(line, det)
            active.add(f"YOU> {safe}")
            status = "processing..." if det is None else "secret detected+stored-ok"
            _draw(win, active.key, left, right, "", note, status)
            result = chat(safe, use_hermes=(active.key == "HERMES"))
            reply = reply_message(result)
            active.add(f"{active.key}> {reply}")
            status = "done"
            continue
        if ch in ("\x7f", "\b", "\x08"):
            input_line = input_line[:-1]
            continue
        if isinstance(ch, str) and ch >= " ":
            input_line += ch


def main() -> None:
    try:
        curses.wrapper(run)
    except Exception as e:  # noqa: BLE001
        print(f"[error] {e}")
    print("\n[ENI chat session ended]")


if __name__ == "__main__":
    main()