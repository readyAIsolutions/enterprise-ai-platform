# Monitor Sources vs Virtual Sources: The Electron App Visibility Problem

## The Problem

**PipeWire monitor sources (`.monitor`) are invisible to Electron-based applications** (Discord, Signal, Chrome, VS Code, Slack, etc.) in their microphone/input device dropdowns.

```bash
pactl list short sources
# Shows:
# 608  MicPlusDesktop.monitor  PipeWire  float32le 2ch 48000Hz  RUNNING
```

But in Discord/Signal Settings → Voice & Video → Microphone: **NOT LISTED**

## Why

- Monitor sources are **sources** (capture devices) that mirror a sink's output
- Electron apps enumerate input devices via PulseAudio/PipeWire API
- Monitor sources have `media.class = "Audio/Sink"` (they're "monitor of a sink") rather than `media.class = "Audio/Source/Virtual"`
- The PulseAudio API exposed to sandboxed apps may filter out monitor sources
- Flatpak/Snap sandboxes add another layer of device enumeration filtering

## The Fix: `module-remap-source`

Creates a **real virtual source** (`media.class = Audio/Source/Virtual`) that remaps the monitor source. Electron apps see this as a regular microphone.

```bash
pactl load-module module-remap-source \
  master=MicPlusDesktop.monitor \
  source_name=MicPlusDesktopSource \
  source_properties=device.description="Mic + Desktop Audio (SELECT THIS)" \
  node.name=MicPlusDesktopSource
```

**Result:**
```bash
pactl list short sources | grep -i micplus
# 608  MicPlusDesktop.monitor     PipeWire  float32le 2ch 48000Hz  RUNNING
# 823  MicPlusDesktopSource       PipeWire  float32le 2ch 48000Hz  IDLE     ← APPS SEE THIS
```

In Discord/Signal: **"Mic + Desktop Audio (SELECT THIS)"** now appears in the microphone dropdown.

## Complete Working Pattern

```bash
# 1. Virtual sink for desktop audio sharing
pactl load-module module-null-sink \
  media.class=Audio/Sink \
  sink_name=DesktopAudioShare \
  sink_properties=device.description="Desktop Audio Share" \
  node.name=DesktopAudioShare

# 2. Combined sink: mic + desktop audio
pactl load-module module-null-sink \
  media.class=Audio/Sink \
  sink_name=MicPlusDesktop \
  sink_properties=device.description="Mic + Desktop Audio (SELECT THIS)" \
  node.name=MicPlusDesktop

# 3. Loopback: desktop audio → combined
pactl load-module module-loopback source=DesktopAudioShare.monitor sink=MicPlusDesktop latency_msec=20

# 4. Loopback: real mic → combined
pactl load-module module-loopback source="$DEFAULT_MIC" sink=MicPlusDesktop latency_msec=20

# 5. VIRTUAL SOURCE (not monitor!) — Electron apps can see this!
pactl load-module module-remap-source \
  master=MicPlusDesktop.monitor \
  source_name=MicPlusDesktopSource \
  source_properties=device.description="Mic + Desktop Audio (SELECT THIS)" \
  node.name=MicPlusDesktopSource
```

## Usage in Apps

| App | Setting | Select |
|-----|---------|--------|
| Discord | Voice & Video → Input Device | **Mic + Desktop Audio (SELECT THIS)** |
| Signal | Settings → Voice & Video → Microphone | **Mic + Desktop Audio (SELECT THIS)** |
| OBS | Audio Input Capture → Device | **Mic + Desktop Audio (SELECT THIS)** |
| Chrome/Meet/Teams | Microphone permission prompt | **Mic + Desktop Audio (SELECT THIS)** |

In `pavucontrol` → Playback: route any app (browser, game, Spotify) to **Desktop Audio Share** to share its audio.

## Verification

```bash
# Should show BOTH the monitor AND the virtual source
pactl list short sources | grep -E 'DesktopAudioShare|MicPlusDesktop'

# Test recording from the virtual source (apps will use this)
pw-record --target=MicPlusDesktopSource /tmp/test.wav --duration=3
pw-play /tmp/test.wav  # Should play back your mic + any desktop audio
```

## "It only shows System default and nothing else" (Electron apps)

Discord/Signal/Chrome input dropdowns may show ONLY "System / Default", hiding even the
working `MicPlusDesktopSource` virtual source. This is NOT a broken setup:

- The app collapses the node that WirePlumber has marked as the default system input into
  a single `System Default` entry. Audio still flows correctly through the combined sink /
  virtual source — you can verify it works from the OS side with `pw-record --target=...`.
- It enumerates every node the app can see, but only non-default ones appear as named
  entries. If your combined sink is the default, it shows as `System Default`.
- To expose the virtual source as its own explicit entry, launch the app targeting that
  specific node instead of the system default (e.g. port-name for OBS, or set the app's
  ALSA/Pulse device to `MicPlusDesktopSource`), OR make a real physical device the default
  input and set the virtual source non-default so it always shows by name.

Use `pavucontrol → Recording` to confirm the app is actually grabbing the right monitor
before concluding the routing failed — the dropdown label can lie.

## Cleanup: too many audio ports from setup attempts

PipeWire `~/.config/pipewire/pipewire.conf.d/*.conf` drop-ins persist virtual devices across
reboots. Leftover drop-ins from earlier experiments keep creating junk ports (e.g. an old
`99-signal-virtual.conf` spawning `signal-sink`/`signal-source` long after that setup is
obsolete). To declutter:

```bash
# 1. List every drop-in that creates devices
for f in ~/.config/pipewire/pipewire.conf.d/*.conf; do
  echo "### $f"; grep -E 'node.name|node.description' "$f"
done
# 2. Delete obsolete ones (keep only the current setup's file)
rm -f ~/.config/pipewire/pipewire.conf.d/99-stale.conf
# 3. Reload to drop the now-orphaned devices
systemctl --user restart pipewire pipewire-pulse
# 4. Re-run your setup service to rebuild combine/loopback/remap
systemctl --user restart audio-sharing-setup.service
```

Only remove the legacy drop-in's devices; the active combined-stream helpers
(`DesktopAudioShare`, `MicPlusDesktop`, `HearLocallyPlusStream`, `MicPlusDesktopSource`)
and real ALSA hardware must stay. Verify with `pactl list short sinks` / `pactl list short sources`.

## PITFALL: never `pkill -f discord` to bounce the app

A broad `pkill -f discord` / `pkill discord` pattern matched this agent's own shell and
killed it (signal −15 / −9), aborting the whole command. Kill the app by its exact binary
path instead, and age out only those match:
`pkill -9 -f '/usr/bin/discord'` (or run `pgrep -a discord` first and kill specific PIDs).

## Related Files

- `audio-sharing-systemd-service.md` — full systemd service with cleanup + remap-source
- `signal-flatpak-mic-monitor-issue.md` — Signal Snap specific issues (use Flatpak)