# PipeWire Adapter Factory Reference

## Factory: `support.null-audio-sink`

Creates a null audio sink/source node. Despite the name "sink", it can create both sinks and sources via the adapter factory.

### Key Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `factory.name` | string | Must be `support.null-audio-sink` |
| `node.name` | string | Unique node identifier |
| `node.description` | string | Human-readable name in pavucontrol/apps |
| `media.class` | string | **Critical**: determines device tab/category |
| `audio.channels` | int | Channel count (2 for stereo) |
| `audio.position` | array | Channel map, e.g. `[ FL, FR ]` |
| `monitor.passthrough` | bool | **Required for sources**: enables capture passthrough |
| `adapter.auto-port-config` | object | Port configuration for adapter |

### Media Class Values

| Class | Appears In | Use Case |
|-------|------------|----------|
| `Audio/Sink` | Output/Speakers tab | Virtual output device |
| `Audio/Source` | Input/Microphone tab | Virtual microphone (standard) |
| `Audio/Source/Virtual` | Input/Microphone tab | **Virtual microphone with monitor passthrough** |
| `Audio/Sink/Virtual` | Output/Speakers tab | Virtual output with special handling |

### Creating a Virtual Microphone (Source)

```ini
{ factory = adapter
    args = {
        factory.name = support.null-audio-sink
        node.name = my-virtual-mic
        node.description = "My Virtual Microphone"
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
```

### Creating a Virtual Speaker (Sink)

```ini
{ factory = adapter
    args = {
        factory.name = support.null-audio-sink
        node.name = my-virtual-speaker
        node.description = "My Virtual Speaker"
        media.class = Audio/Sink
        audio.channels = 2
        audio.position = [ FL FR ]
    }
}
```

### Why `module-null-sink` Fails for Microphones

`pactl load-module module-null-sink source_name=...` creates a monitor source with `media.class = Audio/Sink` (inherited from sink). PipeWire/PulseAudio categorizes it as a **monitor of a sink**, not a standalone source → appears in **Speakers/Output** tab, not **Microphone/Input**.

The adapter factory with `media.class = Audio/Source/Virtual` creates a **true source node** that applications recognize as a microphone.

### Debug Commands

```bash
# List all factories
pw-cli ls Factory

# Inspect adapter factory
pw-dump | jq '.[] | select(.type=="PipeWire:Interface:Factory" and .props["factory.name"]=="adapter")'

# List nodes with media.class
pw-dump | jq '.[] | select(.type=="PipeWire:Interface:Node") | {name: .info.props["node.name"], class: .info.props["media.class"], desc: .info.props["node.description"]}'

# Test virtual sink
pw-play --target=virtual-sink /usr/share/sounds/gnome/default/alarms/ping-ping.oga

# Test virtual source capture
pw-record --target=virtual-source /tmp/test.wav -n 48000
pw-play /tmp/test.wav
```