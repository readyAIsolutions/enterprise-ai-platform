# Signal Snap vs Flatpak: PipeWire Monitor Source Visibility

## Problem

**Signal installed via Snap (`signal-desktop`) does not see PipeWire virtual monitor sources** (e.g., `MicPlusDesktop.monitor`, `DesktopAudioShare.monitor`) in its microphone dropdown.

## Root Cause

The Snap sandbox restricts PipeWire device enumeration. While `pactl list sources` shows the monitor sources at the system level, the Snap-confined Signal process cannot enumerate them via the PipeWire/PulseAudio API exposed inside the sandbox.

- `audio-record` interface is connected (checked via `snap connections signal-desktop`)
- But monitor sources (which are **sources**, not sinks) may not be exposed through the same path

## Solution

**Use the Flatpak version of Signal instead:**

```bash
snap remove signal-desktop
flatpak install flathub org.signal.Signal
```

The Flatpak version uses `xdg-desktop-portal` for device access and correctly sees all PipeWire virtual devices including monitor sources.

## Verification

After switching to Flatpak:

```bash
# Monitor sources should appear in Signal Settings → Voice & Video → Microphone
pactl list short sources | grep -E 'DesktopAudioShare|MicPlusDesktop'
# Should show:
# 601  DesktopAudioShare.monitor  PipeWire  float32le 2ch 48000Hz  IDLE
# 608  MicPlusDesktop.monitor     PipeWire  float32le 2ch 48000Hz  RUNNING
```

## Autostart Entry for Flatpak Signal

```ini
# ~/.config/autostart/signal.desktop
[Desktop Entry]
Type=Application
Name=Signal
Exec=flatpak run org.signal.Signal --start-in-tray
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
StartupWMClass=Signal
Comment=Private messaging from your desktop
```

## Related

- Discord (Snap) **does** see monitor sources correctly — only Signal Snap has this issue
- If you must use Snap Signal, no known workaround; PipeWire virtual monitor sources are fundamentally invisible to it
- The `xdg-desktop-portal` service must be running for Flatpak device access (enabled by default on Ubuntu 24.04+)