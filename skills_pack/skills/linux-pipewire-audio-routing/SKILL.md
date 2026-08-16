---
name: linux-pipewire-audio-routing
category: linux-desktop
description: Create and manage PipeWire virtual audio devices (null sinks, combined sinks, monitor sources) for routing desktop audio to streaming/recording apps like Signal, Discord, OBS. Covers persistent drop-in config, runtime verification, and common routing patterns.
---

# PipeWire Virtual Audio Device Setup

## Quick pointers (read these first)
- **Boot persistence + WirePlumber defaults** — see `references/wireplumber-persistence-boot.md` for the 3-layer stack (PipeWire drop-in sinks + safe WP fallback + boot service) and the "all audio broke in everything = default sink is a virtual null sink" root cause.
- **End-to-end verify** — run `scripts/verify-audio-streaming.sh` to prove audio reaches physical output AND streams as the mic (not just config-checks).
- **systemd service + pactl module pattern** — `references/audio-sharing-systemd-service.md` (boot timing, idempotency, `module-combine-sink`).

## Trigger Conditions
- User wants to route desktop audio to a streaming/recording app (Signal, Discord, OBS, etc.)
- User reports "streaming broke all my audio everywhere" / sudden total silence
- User wants audio to survive every boot without breaking normal playback

## FIRST: The "all audio broken" failure mode (check this before anything else)
- Run `pactl get-default-sink` immediately. **If the default sink is a virtual-only null sink** (MicPlusDesktop, DesktopAudioShare, signal-sink), that is the bug: a null sink has NO physical output, it only feeds `.monitor` capture. Every app plays into a void = system-wide silence. This is the #1 "streaming fucks my audio" report.
- Fix: default must be a **combined** sink (`module-combine-sink` slaves=physical_output,MicPlusDesktop) so audio plays locally AND streams, or the physical sink alone. Never a bare virtual sink.
- Persist virtual sinks via a **PipeWire drop-in** (`~/.config/pipewire/pipewire.conf.d/98-desktop-audio-share.conf`, `support.null-audio-sink` context.objects) so they exist every boot BEFORE any service runs. Service then only adds loopbacks/combine/remap + sets defaults.
- Re-run `scripts/verify-audio-routing.sh` to get a PASS/FAIL verdict on both sinks and the default.
- User needs a virtual sink that can be monitored (for recording) while also hearing audio
- User needs a combined sink that outputs to multiple devices simultaneously
- Persistent PipeWire config via drop-in files (`~/.config/pipewire/pipewire.conf.d/`)

## Core Patterns

### 1. Null Sink (Monitor Source Only)
Routes audio to a monitor source for recording/streaming **without** local playback.

```ini
# ~/.config/pipewire/pipewire.conf.d/99-signal-null.conf
context.modules = [
  { name = libpipewire-module-null-sink
    args = {
      sink_name = signal-sink
      sink_properties = {
        "node.name" = "signal-sink"
        "node.description" = "Signal Virtual Sink"
        "media.class" = "Audio/Sink"
        "channel-positions" = "[ FL FR ]"
      }
    }
  }
]
```

**Monitor source**: `signal-sink.monitor` (select this in Signal/Discord/OBS as input device)

### 2. Combined Sink (Hear + Stream Simultaneously)
Outputs to physical device **and** a null sink — hear locally while streaming.

```ini
# ~/.config/pipewire/pipewire.conf.d/99-combined-sink.conf
context.modules = [
  { name = libpipewire-module-combine-stream
    args = {
      combine.name = combined-sink
      combine.properties = {
        "node.name" = "combined-sink"
        "node.description" = "Combined: Volt 2 + Signal"
        "media.class" = "Audio/Sink"
      }
      combine.streams = [
        { name = "Volt 2 Output" node.name = "alsa_output.usb-Universal_Audio_Volt_2-00.analog-stereo" }
        { name = "Signal Sink" node.name = "signal-sink" }
      ]
    }
  }
]
```

**Set as default sink** so all apps route through it automatically.

### 3. Verification Commands
```bash
# List all sinks
pactl list short sinks

# List monitor sources (for recording input)
pactl list short sources | grep monitor

# Test: play tone to combined sink
pw-play --target=combined-sink /usr/share/sounds/freedesktop/stereo/audio-test-signal.oga

# Monitor signal-sink.monitor (record test)
pw-record --target=signal-sink.monitor /tmp/test.wav --duration=3
pw-play /tmp/test.wav
```

### 4. Apply Config & Restart
```bash
systemctl --user restart pipewire pipewire-pulse wireplumber
# or
pw-cli reload-config
```

## Common Patterns

| Use Case | Sink Type | Monitor Source | Default Sink? |
|----------|-----------|----------------|---------------|
| Stream to Signal/Discord only | Null sink | `signal-sink.monitor` | No (set per-app) |
| Hear locally + stream | Combined sink | `signal-sink.monitor` | Yes |
| Record desktop audio only | Null sink | `desktop-sink.monitor` | No |
| Multiple outputs (headphones + speakers) | Combined sink | N/A | Yes |

## Pitfalls & Fixes

| Issue | Fix |
|-------|-----|
| Monitor source not showing in app | Restart PipeWire: `systemctl --user restart pipewire pipewire-pulse wireplumber` |
| Combined sink not appearing | Check `node.name` of physical sink: `pactl list short sinks` |
| Audio crackling | Match sample rates: `pw-metadata -n settings 0 clock.force-rate 48000` |
| Config not persisting | Use drop-in dir: `~/.config/pipewire/pipewire.conf.d/` (not main config) |
| App doesn't see monitor | Restart the app after PipeWire restart |
| **Signal (Snap) doesn't see monitor sources** | **Use Flatpak Signal (`flatpak install flathub org.signal.Signal`) + `flatpak override --socket=pulseaudio org.signal.Signal`; Snap Signal has PipeWire monitor source visibility issues** |
| Duplicate modules on re-run | Unload by sink_name before creating (see `audio-sharing-systemd-service.md` for cleanup pattern) |
| Device description with spaces breaks module args | Use underscores in `device.description` (e.g., `Mic_Plus_Desktop_Audio_SELECT_THIS`) |
| PipeWire ignores `node.description` from `pactl load-module` | Use `pw-metadata 0 default.metadata.node <NODE_ID> '{"node.description":"..."}'` after creation |
| **`module-loopback` using `@DEFAULT_SOURCE@` or `get-default-source` breaks when user changes default mic** | **HARDCODE the specific ALSA source (e.g., `alsa_input.usb-Universal_Audio_Volt_2_...HiFi__Mic1__source`) — find with `pactl list short sources | grep -i volt`** |
| **Signal autostarts before audio service creates virtual mic** | **Restart Signal after login, or add `ExecStartPost` to service to kill/restart Signal, or manually restart once per boot** |
| **Idempotency check matches wrong loopback** | **Check for the specific REAL_MIC loopback (`${REAL_MIC}.*MicPlusDesktop`), not generic `MicPlusDesktop.*latency_msec=20`** |
| **Electron apps (Discord, Signal, Chrome) don't see monitor sources** | **Create real virtual source with `module-remap-source` — monitors are `media.class=Audio/Sink`, virtual sources are `media.class=Audio/Source/Virtual`** |
| **Flatpak Signal still don't see device in Signal mic dropdown** | **Verify `pw-metadata` ran, restart Signal Flatpak, check `pactl list sources | grep MicPlusDesktopSource`** |
| **`module-loopback` using `@DEFAULT_SOURCE@` or `get-default-source` breaks when user changes default mic** | **HARDCODE the specific ALSA source (e.g., `alsa_input.usb-Universal_Audio_Volt_2_...HiFi__Mic1__source`) — find with `pactl list short sources | grep -i volt`** |
| **Combined sink volume >100% causes clipping/distortion** | **Keep `MicPlusDesktop` (combined sink) at ≤1.0 (100%). Volume >1.0 on null sinks clips before reaching monitor source. Reset: `pactl set-sink-volume MicPlusDesktop 1.0`** |
| **Boot timing race: real USB mic not enumerated when systemd service runs** | **Add wait loop in script (30 retries × 0.5s) before creating mic loopback — mic appears ~5-15s after PipeWire "active"** |
| **`module-combine-stream` syntax fails with "No such entity"** | **Use `module-combine-sink` instead — simpler `slaves="sink1,sink2"` syntax works reliably** |
| **Loopback module creation races sink readiness** | **Retry loop: 5 attempts × 0.5s before giving up** |
| **Idempotency misses missing virtual source** | **Check for `MicPlusDesktopSource` in sources, not just sinks** |

## Verification Checklist
- [ ] `pactl list short sinks | grep -E 'signal-sink|combined-sink'` shows both
- [ ] `pactl list short sources | grep monitor` shows `.monitor` sources
- [ ] Audio plays through physical device when combined sink is default
- [ ] Target app (Signal/Discord/OBS) sees monitor source as input device
- [ ] `pw-record --target=signal-sink.monitor` captures audio

## References
- PipeWire docs: `man pipewire.conf`, `man pw-cli`
- `pactl list modules` — list loaded modules
- `pw-dump` — full graph dump for debugging

## Support Files
- `references/signal-combined-sink.conf` — ready-to-drop combined sink config (Volt 2 + Signal)
- `references/audio-sharing-systemd-service.md` — systemd service + pactl load-module pattern (with improved naming: DesktopAudioShare, MicPlusDesktop)
- `references/signal-flatpak-mic-monitor-issue.md` — **Signal Snap cannot see PipeWire monitor sources; use Flatpak version**
- `references/monitor-source-vs-virtual-source.md` — **CRITICAL: Monitor sources (`.monitor`) are invisible to Electron apps; use `module-remap-source` to create real virtual sources**
- `scripts/verify-audio-routing.sh` — runnable verification script

## Discord & Signal Autostart (Flatpak Signal, Snap Discord)

**Signal Snap cannot see PipeWire virtual sources** — use Flatpak Signal (`flatpak install flathub org.signal.Signal`).

**CRITICAL ORDERING ISSUE**: Signal/Discord auto-start on login *before* the audio-sharing systemd service runs. The virtual mic (`MicPlusDesktopSource`) won't exist when Signal starts, so Signal won't see it. Fix: restart Signal after login, OR add a `ExecStartPost` in the service that restarts Signal, OR manually restart Signal once after boot. The service is `Type=oneshot` with `RemainAfterExit=yes`, so it runs to completion before the desktop session is fully up.

Create `.desktop` files in `~/.config/autostart/` for boot launch:

**`~/.config/autostart/discord.desktop`**
```ini
[Desktop Entry]
Type=Application
Name=Discord
Exec=/snap/bin/discord --start-minimized
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
StartupWMClass=discord
Comment=All-in-one voice and text chat for gamers
```

**`~/.config/autostart/signal.desktop` (Flatpak version — see [Signal Flatpak issue](references/signal-flatpak-mic-monitor-issue.md))**
```ini
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

**Workaround for Signal not seeing virtual mic on first login**: Add to your shell profile (`.bashrc`, `.zshrc`) or a startup script:
```bash
# Restart Signal after audio service is up (runs once per login)
flatpak kill org.signal.Signal 2>/dev/null; flatpak run org.signal.Signal --start-in-tray &
```

## xdg-desktop-portal Configuration (Screen Sharing)
For PipeWire screen sharing to work in Snap/Flatpak apps:
```ini
# ~/.config/xdg-desktop-portal/portals.conf
[preferred]
default=gtk
org.freedesktop.impl.portal.ScreenCast=gtk
org.freedesktop.impl.portal.Screenshot=gtk
org.freedesktop.impl.portal.FileChooser=gtk
```
Ensure `xdg-desktop-portal-gtk` is installed and the user services are enabled:
```bash
systemctl --user enable --now xdg-desktop-portal xdg-desktop-portal-gtk
```

## Alternative: Systemd Service + pactl load-module

For users who prefer dynamic module loading at boot (e.g., existing scripts, simpler syntax, `module-loopback` for mic+desktop combining):

**2. Create a setup script** (e.g., `~/setup-audio-share.sh`):
```bash
#!/bin/bash
# Desktop Audio Sharing for Discord & Signal
# Creates virtual audio devices so you can share desktop audio in calls
set -e

echo "=== Setting up desktop audio sharing ==="

# CLEANUP: unload any existing modules for these sinks (prevents duplicates on re-run)
for mod in $(pactl list short modules | awk '/module-null-sink.*sink_name=(DesktopAudioShare|MicPlusDesktop)/ {print $1}'); do
    pactl unload-module "$mod" 2>/dev/null || true
done
for mod in $(pactl list short modules | awk '/module-loopback.*sink=(DesktopAudioShare|MicPlusDesktop)/ {print $1}'); do
    pactl unload-module "$mod" 2>/dev/null || true
done
for mod in $(pactl list short modules | awk '/module-remap-source.*source_name=MicPlusDesktopSource/ {print $1}'); do
    pactl unload-module "$mod" 2>/dev/null || true
done

# Create virtual sink — route any app's audio here to share it
# Use underscores in device.description to avoid module argument parsing issues
pactl load-module module-null-sink \
  media.class=Audio/Sink \
  sink_name=DesktopAudioShare \
  sink_properties=device.description="Desktop_Audio_Share" \
  node.name=DesktopAudioShare

# Create combined sink — mic + desktop audio merged (THIS IS THE ONE YOU SELECT IN DISCORD/SIGNAL)
pactl load-module module-null-sink \
  media.class=Audio/Sink \
  sink_name=MicPlusDesktop \
  sink_properties=device.description="Mic_Plus_Desktop_Audio_SELECT_THIS" \
  node.name=MicPlusDesktop \
  node.description="Mic_Plus_Desktop_Audio_SELECT_THIS"

sleep 0.5

# Get default mic — WARNING: @DEFAULT_SOURCE@ is fragile! It re-evaluates when user changes
# default input in Discord/Signal/system settings, switching mic to webcam/other device.
# HARDCODE your specific mic source instead (e.g., Volt 2 Mic1):
# DEFAULT_MIC="alsa_input.usb-Universal_Audio_Volt_2_22232037058502-00.HiFi__Mic1__source"
# Find yours: pactl list short sources | grep -i volt
DEFAULT_MIC=$(pactl get-default-source)
echo "Using mic: $DEFAULT_MIC"

# Loopback: desktop audio share → combined
pactl load-module module-loopback source=DesktopAudioShare.monitor sink=MicPlusDesktop latency_msec=20

# Loopback: real mic → combined
pactl load-module module-loopback source="$DEFAULT_MIC" sink=MicPlusDesktop latency_msec=20

# CRITICAL: Virtual source (not monitor!) — Electron apps CAN see this
# Monitor sources (.monitor) are invisible to Discord, Signal, Chrome, etc.
pactl load-module module-remap-source \
  master=MicPlusDesktop.monitor \
  source_name=MicPlusDesktopSource \
  source_properties=device.description="Mic_Plus_Desktop_Audio_SELECT_THIS" \
  node.name=MicPlusDesktopSource

# Fix description propagation: PipeWire doesn't always pick up source_properties from pactl
# Use pw-metadata to force node/device description on the created nodes
sleep 0.5
for NODE_ID in $(pw-cli ls Node | awk '/node.name = "MicPlusDesktop"/ {getline; print $2}' | sed 's/,//'); do
    pw-metadata 0 default.metadata.node "$NODE_ID" '{"node.description":"Mic_Plus_Desktop_Audio_SELECT_THIS"}' >/dev/null 2>&1 || true
done
for NODE_ID in $(pw-cli ls Node | awk '/node.name = "MicPlusDesktopSource"/ {getline; print $2}' | sed 's/,//'); do
    pw-metadata 0 default.metadata.node "$NODE_ID" '{"node.description":"Mic_Plus_Desktop_Audio_SELECT_THIS"}' >/dev/null 2>&1 || true
done

echo ""
echo "✓ Done! Now:"
echo "  1. In Discord/Signal audio settings → select 'Monitor of Mic_Plus_Desktop_Audio_SELECT_THIS' as input"
echo "  2. Open pavucontrol → Playback tab → route any app to 'Desktop_Audio_Share'"
echo "  3. That app's audio will stream through your call"
```

**3. Create systemd user service** (`~/.config/systemd/user/audio-sharing-setup.service`):
```ini
[Unit]
Description=Desktop Audio Sharing Setup (Virtual Sinks for Discord/Signal)
After=pipewire.service pipewire-pulse.service wireplumber.service
Wants=pipewire.service pipewire-pulse.service wireplumber.service

[Service]
Type=oneshot
ExecStart=/home/hunter/setup-audio-share.sh
RemainAfterExit=yes

[Install]
WantedBy=default.target
```

**4. Enable and start:**
```bash
systemctl --user daemon-reload
systemctl --user enable audio-sharing-setup.service
systemctl --user start audio-sharing-setup.service
```

**5. Flatpak Signal needs pulseaudio socket override:**
```bash
flatpak override --socket=pulseaudio org.signal.Signal
# Or system-wide:
sudo flatpak override --socket=pulseaudio org.signal.Signal
```

**6. Autostart Discord (Snap) + Signal (Flatpak) on boot:**

**`~/.config/autostart/discord.desktop`**
```ini
[Desktop Entry]
Type=Application
Name=Discord
Exec=/snap/bin/discord --start-minimized
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
StartupWMClass=discord
Comment=All-in-one voice and text chat for gamers
```

**`~/.config/autostart/signal.desktop`**
```ini
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

```bash
update-desktop-database ~/.local/share/applications
```

**Usage in Discord/Signal:**
- Input device: **Monitor of Mic_Plus_Desktop_Audio_SELECT_THIS** (captures both mic + desktop audio via virtual source)
- In pavucontrol → Playback: route any app to **Desktop_Audio_Share** to share its audio

**Advantages:**
- Simpler syntax for those familiar with PulseAudio/PipeWire CLI
- `module-loopback` handles mic+desktop mixing natively
- `module-remap-source` creates a real virtual source (Electron apps can see it)
- `pw-metadata` ensures descriptions propagate to PipeWire graph
- Cleanup prevents duplicate modules on service restart
- Survives PipeWire restarts (modules reloaded by service)

**Trade-off:** Modules unload on PipeWire restart unless service runs again. The drop-in config approach is more persistent across PipeWire restarts.