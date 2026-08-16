---
name: linux-archive-tools
description: Install and verify archive/compression GUI tools on Linux, including the correct WinRAR-equivalent (there is NO WinRAR GUI for Linux). Covers native GUI archivers (engrampa/file-roller), the rar/unrar/7z command-line binaries, the `unrar` + `p7zip-full` apt packages that give GUI archivers RAR read/write capability, and headless verification of archive operations. Use when the user asks to "install WinRAR", "install an unzip/rar/zip tool", "open .rar files", or otherwise get archive handling working on a Linux desktop.
---

# Linux Archive Tools (the WinRAR situation)

## The core fact (most important)
**There is no WinRAR GUI for Linux.** WinRAR (RARLabs) is Windows-only — it has never shipped a graphical Linux client. The `rarlinux-x64-*.tar.gz` you can download from rarlab is ONLY the `rar`/`unrar` command-line binaries, not a GUI.

When a user says "install WinRAR on Linux", they actually need ONE of:
1. A native Linux GUI archive manager that can open .rar/.zip/.7z (Engrampa, File-Roller, Xarchiver, PeaZip) — this is the real "WinRAR equivalent" GUI.
2. The `rar`/`unrar` CLI binaries for terminal use (creating/extracting RARs).
3. Both.

Do NOT tell the user "WinRAR is installed" when you've only installed CLI binaries. Tell them the GUI is a native Linux app, and set it up so double-clicking a .rar opens it.

## Correct install path (Ubuntu/Debian)
1. **GUI archiver** — usually already present. Check with `command -v engrampa file-roller xarchiver`. If missing, `sudo apt-get install -y engrampa` (MATE) or `file-roller` (GNOME). PeaZip is the most WinRAR-looking GUI if the user wants familiarity.
2. **RAR capability for the GUI** — the GUI archiver needs a backend to actually READ/WRITE RAR. Install:
   - `sudo apt-get install -y unrar`  → full RAR/RAR5 read support (nonfree unrar-nonfree)
   - `sudo apt-get install -y p7zip-full` → 7z/zip/iso handling
   - NOTE: `p7zip-rar` (the RAR codec for 7z) is sometimes NOT in the repos (multiverse missing). Don't depend on it.
3. **CLI rar binary (optional)** — if you want to CREATE RARs from terminal, install from the rarlab tarball: extract, `sudo cp rar/rar /usr/local/bin/rar && sudo cp rar/unrar /usr/local/bin/unrar`. (The apt `unrar` package already provides a working `unrar` at /usr/bin/unrar-nonfree via alternatives.)

## CRITICAL PITFALL: apt batch aborts on one missing package
`apt-get install -y a b c` fails the WHOLE command if even one package name doesn't exist (e.g. `p7zip-rar` absent). It will report only the missing-package error and install NOTHING.

**Always install packages separately or verify each exists first:**
```
sudo apt-get install -y unrar
sudo apt-get install -y p7zip-full
```
Inspect the output — confirm "Setting up <pkg>" lines for each.

## Verify it actually works (headless)
You cannot see a GUI window from a sandbox, but you can prove the GUI archiver launches and handles RAR:

1. **Round-trip test (definitive):**
   ```
   cd /tmp && rar a demo.rar somefile && 7z l demo.rar && mkdir out && unrar x -o+ demo.rar out/
   ```
   - `rar a` creates RAR5
   - `7z l` lists it (proves 7z backend reads RAR)
   - `unrar x` extracts it (proves unrar backend works)

2. **GUI launch check (no DISPLAY needed to detect crash):**
   ```
   timeout 4 env DISPLAY=:0 engrampa /tmp/demo.rar >/tmp/eng.log 2>&1
   # exit=124 means it stayed open (launched fine). Check /tmp/eng.log for CRITICAL/error lines.
   ```
   Empty log = clean launch.

3. **Confirm MIME registration** — the GUI archiver's .desktop should list `application/x-rar` and `application/x-rar-compressed` in its `MimeType=` line, so double-clicking a .rar opens it. Check: `grep -i rar /usr/share/applications/engrampa.desktop`.

## What the user gets
- Double-click any .rar/.zip/.7z in the file manager → opens in Engrampa (or default archiver).
- Open the archiver from the apps menu, File → Open.
- Terminal: `rar a archive.rar <files>` / `unrar x archive.rar`.

## Cleanup after install
- Remove duplicate downloads and extracted temp folders from ~/Downloads unless the user wants the tarball kept.
- Prefer leaving the original downloaded tarball if the user sourced it themselves.

## References
- `references/winrar-linux-myth.md` — the full explanation of why WinRAR has no Linux GUI and the exact equivalents, for when a user is confused or insists.
