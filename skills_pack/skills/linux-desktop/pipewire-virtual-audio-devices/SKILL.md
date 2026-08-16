---
name: pipewire-virtual-audio-devices
description: Create virtual audio sinks/sources on PipeWire using the adapter factory with support.null-audio-sink. Critical for routing desktop audio to applications like Signal, Discord, OBS that only accept microphone/input devices.
category: linux-desktop
---

# PipeWire Virtual Audio Devices

Create virtual audio devices on PipeWire that appear correctly in application device pickers (Signal, Discord, OBS, Chrome, Zoom, etc.).

## The Problem

Applications categorize audio devices by `media.class`:
- **Speakers/Output tab**: `Audio/Sink*`
- **Microphone/Input tab**: `Audio/Source*`

PulseAudio's `module-null-sink` creates a monitor source with `media.class = Audio/Sink` — it appears in **Speakers**, not Microphone.

## The Solution

Use PipeWire's `adapter` factory with `support.null-audio-sink` and explicitly set `media.class`:

```ini
# ~/.config/pipewire/pipewire.conf.d/99-virtual-audio.conf
context.objects = [
    # Virtual SINK (appears in Output/Speakers)
    { factory = adapter
        args = {
            factory.name = support.null-audio-sink
            node.name = virtual-sink
            node.description = "Virtual Sink"
            media.class = Audio/Sink
            audio.channels = 2
            audio.position = [ FL FR ]
        }
    }
    # Virtual SOURCE (appears in Input/Microphone) ⭐
    { factory = adapter
        args = {
            factory.name = support.null-audio-sink
            node.name = virtual-source
            node.description = "Virtual Microphone"
            media.class = Audio/Source/Virtual
            audio.channels = 2
            audio.position = [ FL FR ]
            monitor.passthrough = true
            adapter.auto-port-config = {
                mode = dsp
                monitor = true
                position = preserve
            }
        }
    }
]
```

## Key Properties

| Property | Sink | Source |
|----------|------|--------|
| `media.class` | `Audio/Sink` | `Audio/Source/Virtual` |
| `monitor.passthrough` | N/A | `true` (routes sink audio to source) |
| `adapter.auto-port-config.monitor` | N/A | `true` |

## Usage

1. **Restart PipeWire**: `systemctl --user restart pipewire pipewire-pulse wireplumber`
2. **In target app (Signal, Discord, OBS)**: Select "Virtual Microphone" as input device
3. **Route audio**: In pavucontrol → Playback, set source app to "Virtual Sink"
4. **Test**: `pw-play --target=virtual-sink /usr/share/sounds/...`

## Common Patterns

### Signal Desktop - Desktop Audio
```bash
# 1. Create virtual sink + source (config above)
# 2. Signal Settings → Voice & Video → Microphone → "Virtual Microphone"
# 3. pavucontrol → Playback → Browser/Spotify → "Virtual Sink"
```

### OBS - Desktop Audio Capture
```bash
# OBS → Audio Input Capture → Device: "Virtual Microphone"
# pavucontrol → Playback → App → "Virtual Sink"
```

### Discord - Music Bot / Screen Share Audio
```bash
# Discord Settings → Voice & Video → Input Device → "Virtual Microphone"
# pavucontrol → Playback → Music Player → "Virtual Sink"
```

## Troubleshooting

### Device not appearing in Microphone tab
```bash
# Verify media.class
pw-dump | jq '.[] | select(.info.props["node.name"]=="virtual-source") | .info.props["media.class"]'
# Must be: "Audio/Source/Virtual"
```

### No audio passing through
```bash
# Check monitor.passthrough = true in source config
# Verify sink-input exists when playing:
pactl list short sink-inputs
```

### PipeWire fails to start
```bash
# Check syntax
journalctl --user -u pipewire -n 30
# Common: missing comma, wrong quotes, invalid property name
```

## Runtime Module Management

When using `pactl load-module` for virtual sinks/loopbacks at runtime (e.g., in a startup script or systemd oneshot service), modules are tied to the `pipewire-pulse` session and are lost on restart. Always:

1. **Check before loading** (idempotency): `pactl list short modules | grep "desired-module"` before loading
2. **Prefer PipeWire native config** (`~/.config/pipewire/pipewire.conf.d/`) for permanent virtual devices
3. **Use runtime modules only for dynamic routing** (loopbacks between specific sources/sinks)

### Idempotent module loading pattern
```bash
# Only load if not already present
if ! pactl list short modules 2>/dev/null | grep "loopback" | grep -q "RealMic.*CombinedSink"; then
    pactl load-module module-loopback source="$REAL_MIC" sink=CombinedSink latency_msec=20
fi
```

## Pitfalls

1. **Don't use `module-null-sink`** — monitor source has wrong media.class
2. **Must set `monitor.passthrough = true`** on source — otherwise no audio flows
3. **`Audio/Source/Virtual` not `Audio/Source`** — Virtual ensures it's selectable as mic
4. **Restart PipeWire fully** — `systemctl --user restart pipewire pipewire-pulse wireplumber`
5. **App must be restarted** — Signal/Discord cache device list on startup
6. **Never trust `pactl get-default-source` at boot time** — during startup, PipeWire may return a virtual monitor (e.g., `signal-sink.monitor`) as the default source before real hardware initializes. This causes loopback modules to route silence instead of real mic audio. Always enumerate real ALSA sources explicitly and filter out `.monitor` suffixes. Symptom: user can't be heard in calls despite mics working perfectly. Fix: check `systemctl --user status audio-sharing-setup` logs for "Using mic:" lines — if it picked a monitor, rewrite the script to use explicit device names.
7. **Verify loopback modules survived boot** — after startup, confirm ALL expected loopbacks are loaded with `pactl list short modules | grep loopback`. Common silent failure: the "real mic → combined sink" loopback is missing while desktop-audio loopbacks load fine, because the former needs a real hardware source that may not be ready when the script runs.

## References

- `references/pipewire-adapter-factory.md` — Full factory syntax and examples
- `references/media-class-values.md` — Complete media.class taxonomy
- `references/combined-sink-loopback-pattern.md` — Complete idempotent setup script for mic+desktop-audio combined sinks (Discord/Signal/OBS)