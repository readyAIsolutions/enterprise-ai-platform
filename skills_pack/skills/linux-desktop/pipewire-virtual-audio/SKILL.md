---
name: pipewire-virtual-audio
description: Create PipeWire virtual audio devices (sinks/sources) for routing desktop audio to apps like Signal, Discord, OBS, Zoom. Covers null-sink + virtual-source patterns, combined sinks for monitor+stream, persistent config via ~/.config/pipewire/pipewire.conf.d/, and verification with pw-cli/pactl.
tags: [pipewire, audio, virtual-device, desktop-streaming, signal, discord, obs]
version: 1.0.0
---

# PipeWire Virtual Audio Devices for Desktop Streaming

## When to Use
- Stream desktop audio to **Signal** (no built-in desktop audio capture)
- Route audio to **Discord** / **Zoom** / **OBS** as a virtual microphone
- Create "combined" sinks so you hear audio AND stream it simultaneously
- Any app that only sees PulseAudio/PipeWire **input devices** (microphones)

## Core Patterns

### 1. Virtual Microphone (Desktop Audio → App Input)
App sees a **microphone**; you feed it desktop audio.

```ini
# ~/.config/pipewire/pipewire.conf.d/99-virtual-mic.conf
context.objects = [
    { factory = adapter
        args = {
            factory.name     = support.null-audio-sink
            node.name        = virtual-mic-sink
            node.description = "Virtual Mic Sink"
            media.class      = Audio/Sink
            audio.channels   = 2
            audio.position   = [ FL FR ]
        }
    }
    { factory = adapter
        args = {
            factory.name     = support.null-audio-sink
            node.name        = virtual-mic-source
            node.description = "Desktop Audio (Virtual Mic)"
            media.class      = Audio/Source/Virtual
            audio.channels   = 2
            audio.position   = [ FL FR ]
            monitor.passthrough = true
        }
    }
]
```

**Key properties:**
- `media.class = Audio/Source/Virtual` → appears in **Microphone** tab
- `monitor.passthrough = true` → sink's monitor becomes the source

### 2. Combined Sink (Hear + Stream)
Play to this sink → you hear it AND it goes to the virtual mic.

```ini
# Add to same file or separate 99-combined.conf
context.objects = [
    { factory = adapter
        args = {
            factory.name     = support.null-audio-sink
            node.name        = combined-sink
            node.description = "Combined (Speakers + Virtual Mic)"
            media.class      = Audio/Sink
            audio.channels   = 2
            audio.position   = [ FL FR ]
            # WirePlumber will auto-connect slaves via session manager
        }
    }
]
```

Then link slaves (run once or via WirePlumber script):
```bash
pw-cli create-node adapter factory.name=support.null-audio-sink \
  node.name=combined-sink node.description="Combined (Speakers + Virtual Mic)" \
  media.class=Audio/Sink audio.channels=2 audio.position=[FL,FR] \
  node.passive=false \
  monitor.passthrough=false \
  'node.param.Props={ "slaves": ["alsa_output.usb-...", "virtual-mic-sink"] }'
```

**Simpler: use `module-combine-sink` via PulseAudio emulation:**
```bash
pactl load-module module-combine-sink \
  sink_name=combined-sink \
  slaves=alsa_output.usb-...,virtual-mic-sink \
  sink_properties=device.description="Combined_Speakers+VirtualMic"
pactl set-default-sink combined-sink
```

### 3. Persistent PulseAudio Modules (Alternative)
In `~/.config/pipewire/pipewire-pulse.conf.d/99-virtual.conf`:
```ini
pulse.cmd = [
    { cmd = "load-module" args = "module-null-sink sink_name=virtual-mic-sink sink_properties=device.description=\"Virtual_Mic_Sink\" media.class=Audio/Sink source_name=virtual-mic-source source_properties=device.description=\"Desktop_Audio_(Virtual_Mic)\" media.class=Audio/Source" flags = [ ] }
    { cmd = "load-module" args = "module-combine-sink sink_name=combined-sink slaves=alsa_output.usb-...,virtual-mic-sink sink_properties=device.description=\"Combined_Speakers+VirtualMic\"" flags = [ ] }
]
```

## Verification Commands

```bash
# List sinks/sources
pactl list short sinks
pactl list short sources

# Check media.class (must be Audio/Source or Audio/Source/Virtual for mic tab)
pactl list sources | grep -A 3 "virtual-mic-source"

# Test: play to sink, record from source
pw-play --target=virtual-mic-sink /usr/share/sounds/.../test.oga
pw-record --target=virtual-mic-source /tmp/test.wav -n 144000
pw-play /tmp/test.wav
```

## WirePlumber Auto-Linking (Advanced)
Create `~/.config/wireplumber/main.lua.d/50-virtual-devices.lua`:
```lua
-- Auto-link combined sink slaves
rule = {
  matches = {
    { "node.name", "matches", "combined-sink" },
  },
  apply_properties = {
    ["node.target"] = "virtual-mic-sink",
  },
}
table.insert(alsa_monitor.rules, rule)
```

## Common Pitfalls

| Symptom | Cause | Fix |
|---------|-------|-----|
| Shows in **Speakers** not **Microphone** | `media.class = Audio/Sink` on monitor | Use `Audio/Source/Virtual` + `monitor.passthrough=true` |
| "No such file" on restart | Wrong factory name | Use `support.null-audio-sink` via `adapter` factory |
| Audio loops back (hear yourself) | Monitoring enabled on mic | Disable "Listen to this device" in app settings |
| Disappears after reboot | Config in wrong directory | Use `~/.config/pipewire/pipewire.conf.d/` not `/etc/` |
| Two duplicate devices | Old `pactl load-module` + new config | `pactl unload-module <id>` then restart PipeWire |

## Quick Reference: Factory Names
| Purpose | Factory | Media Class |
|---------|---------|-------------|
| Virtual sink (output) | `support.null-audio-sink` | `Audio/Sink` |
| Virtual source (input/mic) | `support.null-audio-sink` | `Audio/Source/Virtual` |
| Combined sink | `support.null-audio-sink` | `Audio/Sink` (with slaves) |

## Apps That Need This Pattern
- **Signal Desktop** — no desktop audio capture, only mic input
- **Discord (Linux)** — can do screen-share audio but not app-only
- **Zoom/Teams/Meet** — virtual mic for system audio
- **OBS** — virtual mic for streaming desktop audio
- **Browser-based recorders** — only see mic input