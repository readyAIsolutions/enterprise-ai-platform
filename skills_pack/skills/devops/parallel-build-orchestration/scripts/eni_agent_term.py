#!/usr/bin/env python3
"""
eni_agent_term.py — PTY bridge that launches an ENI Hermes agent inside a real
pseudo-terminal, pre-types a TASK as the agent's first message (AFTER the REPL
is ready), then hands the live keyboard to LO so he can keep driving the agent
interactively. Also exposes a control FIFO so a MASTER driver (or LO) can pipe
follow-up instructions into the running agent's window at any time.

Why this exists:
  `hermes chat` (the `eni` wrapper) is a prompt_toolkit REPL that REQUIRES a
  real TTY. Piping the task via stdin closes the stream after the first line and
  breaks the REPL. A PTY keeps the agent happy. We must inject the opening task
  ONLY AFTER the REPL has attached its input reader (detect the startup banner),
  otherwise the trailing newline is swallowed and the agent sits at a blank prompt
  — the classic "agent launched but made ZERO API calls" bug.

Usage (called by the parallel-build launcher inside each xfce4-terminal):
  HERMES_CTL_FIFO=/tmp/eni_ctl_NAME python3 eni_agent_term.py "<TASK>" "<WORKDIR>" [EXTRA_HERMES_ARGS...]

The agent command is `eni chat` (the wrapper selects the ENI profile whose
SOUL.md carries LO's persona prompt). Override with HERMES_AGENT_CMD env var.
The control FIFO is OPTIONAL: it must already EXIST (the launcher creates it
with mkfifo) or the bridge silently skips it. Opening it O_RDWR keeps a reader
always present so outside writers never block.
"""
import os
import sys
import pty
import select
import signal
import termios
import fcntl
import struct
import time


def set_winsize(fd):
    try:
        cols, rows = os.get_terminal_size(sys.stdout.fileno())
    except OSError:
        cols, rows = 80, 24
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


def main():
    if len(sys.argv) < 3:
        sys.stderr.write("usage: eni_agent_term.py <TASK> <WORKDIR> [args...]\n")
        sys.exit(2)

    task = sys.argv[1]
    workdir = sys.argv[2]
    extra = sys.argv[3:]
    # --yolo is intentionally dropped: the proxy must always launch an interactive
    # REPL; forwarding --yolo would make the agent one-shot and die. Model/provider
    # flags are kept and forwarded as real CLI args to the agent.
    extra = [a for a in extra if a != "--yolo"]

    agent_cmd = os.environ.get("HERMES_AGENT_CMD", "eni chat").split()
    cmd = agent_cmd + extra

    # Optional control FIFO for live "talk" injection from the outside.
    ctl_fifo = os.environ.get("HERMES_CTL_FIFO", "")
    fifo_fd = None
    if ctl_fifo and os.path.exists(ctl_fifo):
        try:
            fifo_fd = os.open(ctl_fifo, os.O_RDWR | os.O_NONBLOCK)
        except OSError:
            fifo_fd = None

    pid, fd = pty.fork()
    if pid == 0:
        # child: become the agent, attached to a real pty
        try:
            os.chdir(workdir)
        except OSError:
            pass
        try:
            os.execvp(cmd[0], cmd)
        except Exception as e:
            sys.stderr.write(f"eni_agent_term: failed to exec {cmd[0]}: {e}\n")
            os._exit(127)
    else:
        # parent: proxy user terminal <-> agent pty, inject task when ready,
        # and bridge the control FIFO into the agent's input.
        set_winsize(fd)

        task_sent = False
        seen_banner = False
        start = time.time()

        def forward_sig(signum, frame):
            try:
                os.kill(pid, signum)
            except OSError:
                pass

        signal.signal(signal.SIGWINCH, lambda s, f: set_winsize(fd))
        signal.signal(signal.SIGINT, forward_sig)

        user_in = sys.stdin.fileno()
        user_out = sys.stdout.fileno()
        fl = fcntl.fcntl(user_in, fcntl.F_GETFL)
        fcntl.fcntl(user_in, fcntl.F_SETFL, fl | os.O_NONBLOCK)
        user_eof = False

        watch = [fd, user_in]
        if fifo_fd is not None:
            watch.append(fifo_fd)

        while True:
            try:
                r, _, _ = select.select(watch, [], [], 0.1)
            except (OSError, ValueError):
                break

            if fd in r:
                try:
                    data = os.read(fd, 4096)
                except OSError:
                    break
                if not data:
                    # agent closed its pty -> session over
                    break
                # Detect REPL readiness via the Hermes startup banner.
                try:
                    txt = data.decode("utf-8", "replace")
                except Exception:
                    txt = ""
                if not seen_banner and "Hermes Agent" in txt:
                    seen_banner = True
                # Inject the opening task once the REPL is listening (or after a
                # hard fallback timeout in case the banner text changes).
                if (not task_sent) and (seen_banner or (time.time() - start > 12)):
                    try:
                        os.write(fd, (task + "\n").encode())
                    except OSError:
                        pass
                    task_sent = True
                try:
                    os.write(user_out, data)
                except OSError:
                    break

            if fifo_fd is not None and fifo_fd in r:
                try:
                    fdata = os.read(fifo_fd, 4096)
                except OSError:
                    fdata = b""
                if fdata:
                    try:
                        os.write(fd, fdata)
                    except OSError:
                        pass

            if (not user_eof) and (user_in in r):
                try:
                    data = os.read(user_in, 4096)
                except BlockingIOError:
                    continue
                except OSError:
                    user_eof = True
                    continue
                if not data:
                    user_eof = True
                    continue
                try:
                    os.write(fd, data)
                except OSError:
                    break

        try:
            os.waitpid(pid, 0)
        except OSError:
            pass
        os.close(fd)


if __name__ == "__main__":
    main()
