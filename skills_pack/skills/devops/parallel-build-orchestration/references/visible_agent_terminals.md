# Visible ENI-agent terminals (parallel builds)

Condensed technique for launching one visible terminal per build task, each
running a Hermes agent (ENI persona) pre-loaded with its task and kept
interactive. Companion to Step 2b in SKILL.md and `scripts/eni_agent_term.py`.

## Persona hook = profile SOUL.md
- `hermes profile create <name>` creates an isolated profile dir
  `~/.hermes/profiles/<name>/` with its own `SOUL.md` (personality) + `memories/`.
- Put the agent persona in that SOUL.md. That IS the "start the agent with this
  prompt" mechanism — no need to re-paste the huge prompt per call.
- A wrapper `<name>` is created at `~/.local/bin/<name>` =
  `exec hermes -p <name> "$@"`. So `eni chat` launches the persona agent;
  `hermes -p <name> chat` is equivalent.

## hermes chat is a prompt_toolkit REPL — needs a real TTY
- Piping the task via stdin (`echo task | eni chat`) BREAKS it: stdin closes
  after one line and the REPL can no longer read further user input.
- `hermes -z/--oneshot PROMPT` (GLOBAL flag) = single prompt, prints ONLY the
  final response, non-interactive. Good for headless one-shot work.
- `hermes chat -q/--query QUERY` = single query, non-interactive (exits after
  one turn). Also not interactive.
- For an INTERACTIVE agent that already holds its task AND stays driveable, use
  the PTY bridge (`scripts/eni_agent_term.py`).

## PTY bridge pattern (scripts/eni_agent_term.py)
- `pty.fork()` spawns the agent attached to a real pseudo-terminal, so
  prompt_toolkit is satisfied.
- Parent writes `task + "\n"` to the pty master BEFORE the select loop. The pty
  line-discipline buffers it in canonical mode until the REPL reads it, so it
  survives the start race (agent not yet listening).
- Then proxy user-terminal <-> pty master so LO can keep typing.
- BUG FIX (critical): when the controlling terminal hits EOF (user closes input,
  or `</dev/null`), do NOT `break` the whole loop — just set `user_eof=True`,
  stop selecting `user_in`, and KEEP forwarding agent output (`fd` -> stdout)
  until the agent exits. Breaking early black-screens the agent's output.
- SIGWINCH -> `TIOCSWINSZ` on the pty; SIGINT -> forward to agent pid.

## xterm (in-container) vs xfce4-terminal (host launcher)
- In-container visible agent windows: `xterm -bg black -fg white -hold -e bash
  -c '... eni_agent_term.py ...'`. xterm paints directly (no D-Bus). gnome-terminal
  and xfce4-terminal are D-Bus clients and FAIL from the sandbox (server
  unreachable) — they exit 0 but show nothing.
- User's preferred xfce4-terminal + ENI-per-window: ship a host-side launcher
  (`templates/eni_agent_launcher.sh`, copy to `~/Desktop/eni_parallel_build.sh`)
  and tell him to run it from a REAL host terminal on his XFCE desktop. The PTY
  bridge runs identically under either terminal.

## Task list JSON (~/Desktop/eni_build_tasks.json)
```
{"tasks":[{"name","title","workdir","task"}]}
```
Launcher extracts fields with a tiny inline `python3 -c` (no jq dependency) and
opens one terminal per task, JSON-quoting the task (`json.dumps`) so quotes,
backslashes, and `$vars` survive the `bash -c` handoff.

Verify the bridge without a real API call
```bash
HERMES_AGENT_CMD=/tmp/fake_agent.sh python3 ~/.local/bin/eni_agent_term.py \
  --name TEST_MINI \
  --task /tmp/task_test.txt \
  --repl "echo fake" < /dev/null
# expect: task echoed + "AGENT_RECEIVED=[TASK]" + agent output
```
NOTE: `HERMES_AGENT_CMD` is space-split by the bridge, so a fake/test agent must
be a single token (a script path), NOT a quoted `bash -c "..."` string.
