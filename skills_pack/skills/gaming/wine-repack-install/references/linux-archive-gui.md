# Linux archive GUI — "install WinRAR" equivalent

There is NO WinRAR GUI for Linux (Windows-only, no Linux build). When LO asks
to "install WinRAR" or "open/manage .rar on Linux", use the native stack below.

## GUI (WinRAR-like)
- `engrampa` (MATE Archive Manager) — the GUI. Registered for
  `application/x-rar`. Opens .rar/.zip/.7z/.tar/.tar.gz etc.
- Put a launcher on the desktop: `cp` the system `engrampa.desktop` (or the
  existing `~/Desktop/apps/` one) to `~/Desktop/`, `chmod +x`.

## Backend that makes RAR actually work
- `sudo apt-get install -y unrar p7zip-full`
  - `unrar` = nonfree 7.2.4 (full RAR5 read). WITHOUT it, Engrampa silently
    cannot open .rar.
  - `p7zip-full` = .7z/.zip read-write.

## CLI for creating RARs
- WinRAR create capability -> install rar/unrar tarball: extract to
  `/usr/local/bin` (provides `rar` + `unrar`). Verified rar 7.23.
- Extract multi-part repack RARs: `rar x -o+ kas-XXX.part1.rar <outdir>`
  (`-o+` = overwrite existing; part1 only, rar follows the chain).

## Verify (headless box)
- `timeout 4 engrampa <file>.rar; echo exit=$?` -> 124 means it stayed open
  (launched clean). 0/other = problem.
- `which unrar rar engrampa` confirms tooling present.
