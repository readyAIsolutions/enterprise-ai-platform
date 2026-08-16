# Systemd Service + pactl load-module Pattern

Alternative to persistent PipeWire drop-in configs. Use when:
- You have an existing working `pactl load-module` script
- You prefer CLI syntax over PipeWire config syntax
- You need `module-loopback` for mic + desktop audio combining

## Critical (2026-08): the "all audio broken everywhere" failure mode

- **NEVER leave the default sink on a virtual-only null sink.** The biggest report "streaming fucks all my audio in everything" is not a stream bug — it's the default sink being `MicPlusDesktop` (a `module-null-sink`). A null sink has NO physical output: it only feeds its `.monitor` for capture. When the global default sink points at it, every app (games, music, YouTube) plays into a void → total silence system-wide. Diagnose immediately with `pactl get-default-sink`; if it's a virtual/null sink, that's the bug.
- **The default sink should be a COMBINED sink that slaves `physical_output + MicPlusDesktop`** (via `module-combine-sink`) so audio BOTH plays locally AND feeds the stream capture. Fallback: set default to the physical sink alone — never to `MicPlusDesktop` by itself.
- **Boot service must not abort before setting defaults** — use `set +e`, not `set -e`, in the setup script, OR the whole chain dies on one recoverable failure (e.g. a load-module I/O error) and the default sink never gets fixed.
- **Persist virtual sinks via PipeWire drop-in**, not the service — `~/.config/pipewire/pipewire.conf.d/98-desktop-audio-share.conf` creates `DesktopAudioShare` + `MicPlusDesktop` as `support.null-audio-sink` `context.objects`. This guarantees they exist at EVERY boot before any service runs, eliminating the null-sink creation race entirely. The service then only adds loopbacks/combine/remap + sets defaults.
- **Loading new drop-in configs:** `systemctl --user restart pipewire pipewire-pulse` reloads `pipewire.conf.d/*.conf`. Verify with `pactl list short sinks`.

## Key Learnings (July 2026)

- **Clean up existing modules first** — running the script twice (manually + via service) creates duplicate `module-null-sink` and `module-loopback` instances. The updated script below unloads by sink_name before creating.
- **Signal (Snap) has PipeWire monitor source issues** — The snap-packaged Signal Desktop cannot see `*.monitor` sources reliably. Use Flatpak Signal (`org.signal.Signal`) or system package instead. Discord (Snap) works fine.
- **Module latency** — `latency_msec=20` is a good default; increase to 50-100 if you hear crackling.
- **Autostart apps** — `.desktop` files in `~/.config/autostart/` work reliably for Snap apps (Discord, Signal).
- **Device description spaces break module args** — Use underscores in `device.description` (e.g., `Mic_Plus_Desktop_Audio_SELECT_THIS`) because spaces confuse `pactl load-module` argument parsing.
- **pactl properties don't always propagate to PipeWire nodes** — Use `pw-metadata` to set `node.description` and `device.description` on created nodes after module load.
- **Signal Flatpak needs pulseaudio socket** — `flatpak override --socket=pulseaudio org.signal.Signal`

## NEW Learnings (July 2026 - boot timing fixes)

- **Boot timing race: real mic not ready when service runs** — The systemd service runs `After=pipewire.service pipewire-pulse.service wireplumber.service` but the Volt 2 USB mic source (`alsa_input.usb-Universal_Audio_Volt_2_...HiFi__Mic1__source`) isn't enumerated yet. The service starts but the mic source appears ~5-15s later. **Fix: wait loop in script** (30 retries × 0.5s = 15s max wait).
- **module-combine-stream syntax is fragile** — The JSON-like `combine.streams="[ { name=... } ]"` syntax fails with "No such entity". **Use `module-combine-sink` instead** — simpler `slaves="sink1,sink2"` syntax works reliably.
- **Loopback creation can race sink readiness** — Even after sinks exist, `module-loopback` creation may fail with "No such entity". **Fix: retry loop** (5 retries × 0.5s).
- **Idempotency check must verify virtual source too** — Checking only sinks misses missing `module-remap-source` (MicPlusDesktopSource). Added check for `MicPlusDesktopSource` in sources.
- **pw-metadata needed for ALL custom nodes** — Added for HearAndStream combined sink, not just MicPlusDesktop/MicPlusDesktopSource.
- **Service Type=oneshot + RemainAfterExit=yes is correct** — Service shows "active (exited)" after running, survives PipeWire restarts only if service is re-triggered (which it won't be without manual restart or drop-in config).

## Files

### `~/setup-audio-share.sh` (with duplicate cleanup + module-remap-source for Electron app visibility + pw-metadata fix + robust idempotency + @DEFAULT_SOURCE@ cleanup + BOOT TIMING FIXES)

```bash
#!/bin/bash
# Desktop Audio Sharing for Discord & Signal
# Creates virtual audio devices so you can share desktop audio in calls
set -e

echo "=== Setting up desktop audio sharing ==="

# ---- IDEMPOTENCY CHECK ----
# Don't reload if already running (check for our sinks)
if pactl list short sinks 2>/dev/null | grep -q "DesktopAudioShare" && \
   pactl list short sinks 2>/dev/null | grep -q "MicPlusDesktop"; then
    echo "Virtual sinks already exist. Verifying real mic loopback..."

    # Check if the REAL MIC loopback to MicPlusDesktop exists
    REAL_MIC="alsa_input.usb-Universal_Audio_Volt_2_22232037058502-00.HiFi__Mic1__source"
    if ! pactl list short modules 2>/dev/null | grep "loopback" | grep -q "${REAL_MIC}.*MicPlusDesktop"; then
        echo "Re-adding missing real mic loopback..."
    else
        # Also verify combined sink exists
        if ! pactl list short sinks 2>/dev/null | grep -q "HearAndStream"; then
            echo "Combined sink missing — continuing setup..."
        else
            # Also verify virtual source exists
            if ! pactl list short sources 2>/dev/null | grep -q "MicPlusDesktopSource"; then
                echo "Virtual source missing — continuing setup..."
            else
                echo "✓ All good — virtual sinks, loopbacks, combined sink, and virtual source already configured."
                exit 0
            fi
        fi
    fi
fi

# ---- FIND REAL MICROPHONES ----
# Try Volt 2 Mic1 first (preferred), then webcam mic, then any real mic
REAL_MIC=""
for mic in \
    "alsa_input.usb-Universal_Audio_Volt_2_22232037058502-00.HiFi__Mic1__source" \
    "alsa_input.usb-Sunplus_IT_Co_Live_Streamer_CAM_313_20200529002-02.mono-fallback" \
    "alsa_input.usb-Universal_Audio_Volt_2_22232037058502-00.HiFi__Mic2__source"; do
    if pactl list short sources 2>/dev/null | grep -q "$mic"; then
        REAL_MIC="$mic"
        break
    fi
done

if [ -z "$REAL_MIC" ]; then
    # Fallback: use whatever pactl says is the default, but filter out monitors
    REAL_MIC=$(pactl get-default-source)
    if echo "$REAL_MIC" | grep -q "\.monitor"; then
        echo "ERROR: Default source is a monitor ($REAL_MIC) — no real mic found!"
        exit 1
    fi
fi

echo "Using real mic: $REAL_MIC"

# ---- CLEANUP: Remove any old @DEFAULT_SOURCE@ loopback to MicPlusDesktop ----
# This fixes the case where a previous run used the fragile @DEFAULT_SOURCE@
for mod in $(pactl list short modules 2>/dev/null | awk '/module-loopback.*sink=MicPlusDesktop/ {print $1}'); do
    SRC=$(pactl list modules | awk -v m="$mod" '$1=="Module" && $2==m {found=1} found && /source=/ {print $2; exit}' | sed 's/source=//')
    if [[ "$SRC" != "$REAL_MIC" ]]; then
        pactl unload-module "$mod" 2>/dev/null || true
    fi
done

# CLEANUP: unload any existing modules for these sinks (prevents duplicates on re-run)
# Use module index (first column) for reliable unload; sink_name matching can be ambiguous
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
# Use underscores in device.description to avoid module-argument parsing issues with spaces
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

# COMBINED SINK: Hear locally (Volt 2 Line) + stream (MicPlusDesktop)
# Use module-combine-sink (simpler, works reliably) instead of module-combine-stream
VOLT2_LINE="alsa_output.usb-Universal_Audio_Volt_2_22232037058502-00.HiFi__Line__sink"
if ! pactl list short sinks 2>/dev/null | grep -q "HearAndStream"; then
    pactl load-module module-combine-sink \
      sink_name=HearAndStream \
      sink_properties=device.description="Hear_Locally_Plus_Stream" node.name=HearAndStream \
      slaves="$VOLT2_LINE,MicPlusDesktop"
    sleep 0.5
fi

# Set as default so all apps play to both
pactl set-default-sink HearAndStream

sleep 0.5

# ---- LOOPBACKS: route audio sources into the combined sink ----
# Only add if not already loaded

# Desktop audio → combined
if ! pactl list short modules 2>/dev/null | grep "loopback" | grep -q "DesktopAudioShare.monitor.*MicPlusDesktop"; then
    pactl load-module module-loopback source=DesktopAudioShare.monitor sink=MicPlusDesktop latency_msec=20
fi

# Signal virtual audio → combined (for sharing Signal call audio back)
if ! pactl list short modules 2>/dev/null | grep "loopback" | grep -q "signal-sink.monitor.*MicPlusDesktop"; then
    pactl load-module module-loopback source=signal-sink.monitor sink=MicPlusDesktop latency_msec=20
fi

# REAL MIC → combined (CRITICAL — this is your voice!)
# HARDCODED to Volt 2 Mic1 — @DEFAULT_SOURCE@ is fragile (switches to webcam/etc)
REAL_MIC="alsa_input.usb-Universal_Audio_Volt_2_22232037058502-00.HiFi__Mic1__source"

# WAIT for real mic to be available (boot timing issue)
for i in {1..30}; do
    if pactl list short sources 2>/dev/null | grep -q "$REAL_MIC"; then
        break
    fi
    sleep 0.5
done

# CLEANUP: Remove any old @DEFAULT_SOURCE@ loopback to MicPlusDesktop
for mod in $(pactl list short modules 2>/dev/null | awk '/module-loopback.*sink=MicPlusDesktop/ {print $1}'); do
    SRC=$(pactl list modules | awk -v m="$mod" '$1=="Module" && $2==m {found=1} found && /source=/ {print $2; exit}' | sed 's/source=//')
    if [[ "$SRC" != "$REAL_MIC" ]]; then
        pactl unload-module "$mod" 2>/dev/null || true
    fi
done

# Retry loopback creation with retries (boot timing can race)
for i in {1..5}; do
    if pactl load-module module-loopback source="$REAL_MIC" sink=MicPlusDesktop latency_msec=20 2>/dev/null; then
        break
    fi
    sleep 0.5
done

# ---- VIRTUAL SOURCE (appears as microphone to apps) ----
if ! pactl list short sources 2>/dev/null | grep -q "MicPlusDesktopSource"; then
    pactl load-module module-remap-source \
      master=MicPlusDesktop.monitor \
      source_name=MicPlusDesktopSource \
      source_properties=device.description="Mic_Plus_Desktop_Audio_SELECT_THIS" \
      node.name=MicPlusDesktopSource
fi

# FIX: pactl properties don't always propagate to PipeWire node descriptions.
# Use pw-metadata to set node.description + device.description on the created nodes.
sleep 0.5
for NODE_ID in $(pw-cli ls Node | awk -F'[ ,]' '/node.name = "MicPlusDesktop"/ {for(i=1;i<=NF;i++) if($i=="id") print $(i+1)}'); do
    pw-metadata 0 default.metadata.node "$NODE_ID" '{ "node.description": "Mic_Plus_Desktop_Audio_SELECT_THIS", "device.description": "Mic_Plus_Desktop_Audio_SELECT_THIS" }' 2>/dev/null || true
done
for NODE_ID in $(pw-cli ls Node | awk -F'[ ,]' '/node.name = "MicPlusDesktopSource"/ {for(i=1;i<=NF;i++) if($i=="id") print $(i+1)}'); do
    pw-metadata 0 default.metadata.node "$NODE_ID" '{ "node.description": "Mic_Plus_Desktop_Audio_SELECT_THIS", "device.description": "Mic_Plus_Desktop_Audio_SELECT_THIS" }' 2>/dev/null || true
done
for NODE_ID in $(pw-cli ls Node | awk -F'[ ,]' '/node.name = "HearAndStream"/ {for(i=1;i<=NF;i++) if($i=="id") print $(i+1)}'); do
    pw-metadata 0 default.metadata.node "$NODE_ID" '{ "node.description": "Hear_Locally_Plus_Stream" }' 2>/dev/null || true
done
for NODE_ID in $(pw-cli ls Node | awk -F'[ ,]' '/node.name = "DesktopAudioShare"/ {for(i=1;i<=NF;i++) if($i=="id") print $(i+1)}'); do
    pw-metadata 0 default.metadata.node "$NODE_ID" '{ "node.description": "Desktop_Audio_Share", "device.description": "Desktop_Audio_Share" }' 2>/dev/null || true
done

echo ""
echo "✓ Done! Now:"
echo "  1. In Discord/Signal audio settings → select 'Mic_Plus_Desktop_Audio_SELECT_THIS' as input"
echo "  2. Open pavucontrol → Playback tab → route any app to 'Desktop_Audio_Share'"
echo "  3. That app's audio will stream through your call"
echo ""
echo "  Real mic in use: $REAL_MIC"
```

### `~/.config/systemd/user/audio-sharing-setup.service`

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

## Commands

```bash
# Enable on boot
systemctl --user daemon-reload
systemctl --user enable audio-sharing-setup.service
systemctl --user start audio-sharing-setup.service

# Verify
systemctl --user status audio-sharing-setup.service
pactl list short sinks | grep -E 'DesktopAudioShare|MicPlusDesktop'
pactl list short sources | grep -E 'DesktopAudioShare|MicPlusDesktop'
```

## Discord/Signal Setup

1. **Input Device**: Select **Monitor of Mic + Desktop Audio (SELECT THIS)**
2. **pavucontrol → Playback**: Route browser/game/Spotify to **Desktop Audio Share**
3. **pavucontrol → Recording**: Verify Discord/Signal shows **Monitor of Mic + Desktop Audio (SELECT THIS)**

## Notes

- Modules unload if PipeWire restarts. The service runs on user login, so they're recreated.
- For persistence across PipeWire restarts without re-login, use the drop-in config approach (see `signal-combined-sink.conf`).
- `latency_msec=20` reduces latency; increase if you hear crackling.
- `RemainAfterExit=yes` keeps the service "active" so `systemctl status` shows it ran.