# PipeWire Media Class Taxonomy

## Overview

`media.class` is the primary property PipeWire uses to categorize nodes and determine where they appear in UI (pavucontrol, GNOME Settings, application device pickers).

## Standard Media Classes

### Audio Sinks (Output Devices)
| Class | Description | Typical UI Location |
|-------|-------------|---------------------|
| `Audio/Sink` | Physical or virtual output | Output Devices / Speakers tab |
| `Audio/Sink/Virtual` | Virtual output with special routing | Output Devices / Speakers tab |

### Audio Sources (Input Devices)
| Class | Description | Typical UI Location |
|-------|-------------|---------------------|
| `Audio/Source` | Physical microphone/line-in | Input Devices / Microphone tab |
| `Audio/Source/Virtual` | Virtual microphone (monitor passthrough) | **Input Devices / Microphone tab** ⭐ |
| `Audio/Source/Monitor` | Monitor of a sink (auto-created) | Often hidden or in Microphone tab |

### Audio Duplex (Bidirectional)
| Class | Description |
|-------|-------------|
| `Audio/Duplex` | Combined sink+source (headsets, Bluetooth) |
| `Audio/Duplex/Virtual` | Virtual duplex device |

## Application Behavior

### Signal Desktop
- **Microphone dropdown**: Shows nodes with `media.class` starting with `Audio/Source`
- **Speaker dropdown**: Shows nodes with `media.class` starting with `Audio/Sink`
- **Ignores**: `Audio/Source/Monitor` (sometimes), `Audio/Duplex` (split)

### Discord (Linux)
- **Input Device**: `Audio/Source` and `Audio/Source/Virtual`
- **Output Device**: `Audio/Sink` and `Audio/Sink/Virtual`
- Also supports PipeWire screen-share audio via portal

### OBS Studio
- **Audio Input Capture**: `Audio/Source` and `Audio/Source/Virtual`
- **Audio Output Capture**: `Audio/Sink` monitors (via `Audio/Source/Monitor`)

### Chrome/Chromium (WebRTC)
- `getUserMedia({audio: true})` → enumerates `Audio/Source` and `Audio/Source/Virtual`
- Tab audio capture uses PipeWire portal (`Audio/Sink` monitor)

### Zoom / Teams / Meet
- Similar to Signal: `Audio/Source*` for microphone, `Audio/Sink*` for speaker

## Critical Distinction

```
module-null-sink (PulseAudio module)
  ├─ sink: media.class = Audio/Sink
  └─ monitor source: media.class = Audio/Sink  ← WRONG for microphone tab!

adapter factory + support.null-audio-sink
  ├─ sink: media.class = Audio/Sink
  └─ source: media.class = Audio/Source/Virtual  ← CORRECT for microphone tab
```

## Verification

```bash
# Check a node's media.class
pw-dump | jq '.[] | select(.type=="PipeWire:Interface:Node" and .info.props["node.name"]=="virtual-source") | .info.props["media.class"]'

# Should output: "Audio/Source/Virtual"

# List all sources with classes
pw-dump | jq -r '.[] | select(.type=="PipeWire:Interface:Node" and (.info.props["media.class"] | startswith("Audio/Source"))) | "\(.info.props["node.name"]): \(.info.props["media.class"])"'
```