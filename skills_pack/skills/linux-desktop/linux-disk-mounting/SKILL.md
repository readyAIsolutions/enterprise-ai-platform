---
name: linux-disk-mounting
description: Mount external/internal drives so they auto-mount on boot AND appear in file managers (Thunar, Nautilus, Dolphin, Nemo) under Devices. Covers mount point standards (/media vs /mnt), fstab options for user access, udisks2 integration, and file manager daemon restart.
category: linux-desktop
tags: [disk, mount, fstab, thunar, nautilus, dolphin, nemo, udisks2, automount, file-manager]
---

# Linux Disk Mounting for File Manager Visibility

## When to Use
- User adds a new drive and wants it to appear in file manager sidebar (Devices section)
- Drive mounts but doesn't show in Thunar/Nautilus/Dolphin/Nemo
- Need persistent auto-mount on boot with user read/write access
- Mounting NTFS, exFAT, ext4, or other filesystems on Linux desktop

## Core Principle: Mount Point Location Determines File Manager Visibility

| Mount Point | File Manager Visibility | Use Case |
|-------------|------------------------|----------|
| `/media/<user>/<label>` | **YES** — appears under Devices | Removable/external drives, user data |
| `/mnt/<name>` | NO — manual mounts only | System mounts, server shares, temporary |
| `/home/<user>/<name>` | YES — as regular folder | Symlinked from /media, or bind mounts |

**Rule**: For file manager (Thunar/Nautilus/Dolphin/Nemo) to show a drive under **Devices**, the mount point **MUST** be under `/media/<username>/` — this is the udisks2/ GVFS standard.

## Workflow

### 1. Identify the Drive
```bash
lsblk -f
# Note: NAME, FSTYPE, LABEL, UUID
```

### 2. Create Mount Point (Standard Location)
```bash
sudo mkdir -p /media/<username>/<label>
# Example: sudo mkdir -p /media/hunter/Backup
```

### 3. Configure /etc/fstab
```bash
# Get UUID from lsblk -f
UUID=<uuid>  /media/<user>/<label>  <fstype>  defaults,uid=1000,gid=1000,nofail  0  0
```

**Filesystem-specific types:**
- NTFS: `ntfs-3g` (not `ntfs` — kernel driver has issues)
- exFAT: `exfat` (kernel 5.4+) or `exfat-fuse`
- ext4: `ext4`
- FAT32: `vfat`

**Key options:**
- `uid=1000,gid=1000` — user owns files (adjust to your UID)
- `nofail` — boot continues even if drive missing
- `defaults` — rw, suid, dev, exec, auto, nouser, async
- `0 0` — no dump, no fsck on boot

### 4. Mount and Verify
```bash
sudo mount -a
mount | grep <label>
ls -la /media/<user>/<label>
```

### 5. Restart File Manager Daemon
```bash
# Thunar (XFCE)
pkill thunar; thunar --daemon &

# Nautilus (GNOME)
nautilus -q; nautilus --gapplication-service &

# Dolphin (KDE) — usually auto-detects, but:
kquitapp5 dolphin; dolphin &

# Nemo (Cinnamon/Unity)
nemo -q; nemo --desktop &
```

### 6. Optional: Symlink to Home for Easy Access
```bash
ln -sf /media/<user>/<label> ~/<label>
# Example: ln -sf /media/hunter/Backup ~/Backup
```

## Pitfalls

### Mount Point Wrong → No Device Icon
- **Symptom**: Drive mounts (`mount` shows it), but file manager sidebar doesn't list it
- **Cause**: Mounted at `/mnt/` or `/home/` instead of `/media/<user>/`
- **Fix**: Move mount point to `/media/<user>/<label>` in fstab, remount, restart file manager

### NTFS Permission Issues
- **Symptom**: Can't write to NTFS drive as user
- **Cause**: Mounted with root ownership, no uid/gid
- **Fix**: Use `ntfs-3g` driver + `uid=1000,gid=1000` in fstab

### File Manager Doesn't Refresh
- **Symptom**: Drive mounted correctly but still not in sidebar
- **Cause**: File manager daemon caches device list
- **Fix**: Restart the file manager daemon (see step 5)

### Drive Not Present at Boot → Boot Hang
- **Symptom**: System hangs on boot waiting for drive
- **Cause**: Missing `nofail` option in fstab
- **Fix**: Add `nofail` to fstab options

### Wrong Filesystem Type in fstab
- **Symptom**: `mount -a` fails with "wrong fs type"
- **Cause**: Using `ntfs` instead of `ntfs-3g`, or wrong type for exFAT
- **Fix**: Use correct type (see table above)

## File Manager Specifics

### Thunar (XFCE) — Used on LO's Box
- Monitors `/media/<user>/` via GVFS/udisks2
- Daemon: `thunar --daemon`
- Restart: `pkill thunar; thunar --daemon &`
- Also respects `~/.gtk-bookmarks` for sidebar shortcuts

### Nautilus (GNOME)
- Monitors `/media/<user>/` via GVFS
- Daemon: `nautilus --gapplication-service`
- Restart: `nautilus -q` then relaunch

### Dolphin (KDE)
- Uses Solid/UDISKS2, auto-detects most mounts
- Restart: `kquitapp5 dolphin; dolphin &`

### Nemo (Cinnamon)
- Monitors `/media/<user>/` via GVFS
- Daemon: `nemo --desktop` (for desktop icons) or `nemo` (file manager)
- Restart: `nemo -q; nemo &`

## Quick Reference: fstab Templates

```bash
# NTFS external drive
UUID=XXXXXXXXXXXXXXXX  /media/hunter/Backup  ntfs-3g  defaults,uid=1000,gid=1000,nofail  0  0

# exFAT external drive
UUID=XXXX-XXXX  /media/hunter/Data  exfat  defaults,uid=1000,gid=1000,nofail  0  0

# ext4 internal drive
UUID=XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX  /media/hunter/Storage  ext4  defaults,nofail  0  2

# FAT32 USB stick
UUID=XXXX-XXXX  /media/hunter/USB  vfat  defaults,uid=1000,gid=1000,nofail,umask=000  0  0
```

## Verification Checklist
- [ ] `mount | grep <label>` shows correct mount point under `/media/<user>/`
- [ ] `ls -la /media/<user>/<label>` shows user-owned files (not root)
- [ ] File manager sidebar shows drive under **Devices**
- [ ] Can read/write files as user
- [ ] `sudo mount -a` succeeds (no errors)
- [ ] Reboot test: drive appears after restart