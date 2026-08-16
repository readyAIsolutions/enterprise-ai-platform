# WinRAR on Linux — the myth and the reality

## Why users ask for "WinRAR on Linux"
On Windows, WinRAR is the default archive GUI (trial, nag-screen, but ubiquitous).
Users migrating to Linux look for the same app and download `rarlinux-x64-*.tar.gz`
from rarlab thinking it's the Linux WinRAR. It is only the CLI binaries.

## Fact
- RARLabs has NEVER released a graphical WinRAR client for Linux.
- The Linux download (`rarlinux-x64`) contains: `rar` (create RAR), `unrar` (extract),
  `default.sfx`, license, docs. No GUI.
- The `unrar` source is freeware; the `rar` compressor is trial/closed.

## Correct equivalents (what to actually install)
| Need | Linux tool | Notes |
|------|-----------|-------|
| GUI like WinRAR | Engrampa (MATE) | Already installed on many Ubuntu boxes; opens .rar/.zip/.7z/.tar |
| GUI like WinRAR | File-Roller (GNOME) | GNOME Archive Manager |
| GUI like WinRAR (most similar look) | PeaZip | Qt GUI, WinRAR-ish layout, flatpak available |
| Lightweight GUI | Xarchiver | XFCE |
| Open RAR files in GUI | `unrar` apt pkg | nonfree unrar-nonfree gives RAR5 read |
| 7z/zip/iso in GUI | `p7zip-full` apt pkg | |
| Create RAR from terminal | `rar` CLI (rarlab tarball) | copy rar/unrar to /usr/local/bin |
| Extract RAR from terminal | `unrar` CLI | from tarball OR apt pkg |

## How to explain to the user (terse, honest)
"There is no WinRAR GUI for Linux — WinRAR is Windows-only. I installed a native
Linux archive manager (Engrampa) that opens .rar/.zip/.7z just like WinRAR's GUI,
plus the rar/unrar engine so it actually reads RAR files. Double-click any archive
to open it."

## DO NOT
- Say "WinRAR is installed" when only CLI binaries exist.
- Leave the user with only `rar`/`unrar` and no way to double-click a .rar.
- Hard-refuse — just install the correct equivalent and tell them.
