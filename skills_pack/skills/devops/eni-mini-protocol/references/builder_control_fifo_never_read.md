# Builder control FIFOs: never READ them — check existence only (empirically confirmed Aug 2026)

## PITFALL — `cat` / `read_file` on a control FIFO blocks indefinitely
A builder's control FIFO (`/tmp/eni_ctl_<NAME>`) is a NAMED PIPE (`p` in `ls -l`), not a
regular file. The designated writer is the master/PL; until a writer opens it and writes a
directive, any reader that opens it for reading BLOCKS until data arrives.

Observed live: `cat /tmp/eni_ctl_BUILDER_50` hung until the 180s terminal timeout hit
(exit 124), with zero output. `read_file` on a FIFO similarly returns empty/never-resolves.
Do NOT waste a pass (or hang a session) trying to read the directive out of the FIFO.

## CORRECT pattern — probe the pipe, don't read it
A directive's ABSENCE or PRESENCE is decided by existence/type checks, never by reading:

```bash
p=/tmp/eni_ctl_BUILDER_37
[ -e "$p" ] && echo "EXISTS $p"   || echo "NO_ENTRY $p"
[ -p "$p" ] && echo "IS_PIPE $p" || echo "NOT_A_PIPE $p"
```
- `[ -e ]` = the FIFO node exists at all.
- `[ -p ]` = it is actually a named pipe (confirms role).
- If `[ -e ]` is NO_ENTRY, the master never assigned this builder a task → the builder is
  **IDLE** with no directive, and must NOT invent work.
- If it exists and content is genuinely needed, the PL's relay (`eni_ctl_fifo_relay.sh`)
  is the designed path to move directive text — never raw-dump the pipe yourself.

## Why registration of the empty-FIFO state matters
An existing-but-empty FIFO alongside a MISSING one (e.g. `eni_ctl_BUILDER_50` present while
`eni_ctl_BUILDER_37` absent in the same `/tmp`) is itself evidence for an idle builder:
record which sibling FIFOs ARE present so the STATUS card's verification line is specific
("BUILDER_50 + DEMIURGE* FIFOs present, none for BUILDER_37"), which aids fleet forensics.