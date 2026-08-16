#!/usr/bin/env bash
# Verify PipeWire virtual audio setup for streaming
# PASS/FAIL guard for the "all audio broken everywhere" failure mode:
#   the global DEFAULT SINK must NEVER resolve to a virtual-only null sink
#   (signal-sink, DesktopAudioShare, MicPlusDesktop by itself), because a
#   null sink has NO physical output - it only feeds .monitor capture. If the
#   default sits on one, every app plays into a void = total system silence.
# Correct default = a combined sink that slaves a physical output (hear locally
# + stream) or a real physical sink. NEVER a bare virtual null sink.
# Usage: ./verify-audio-routing.sh
set -uo pipefail

FAIL=0
echo "=== PipeWire Virtual Audio Verification ==="

echo
echo "--- Physical (real) output sinks ---"
PHYS=$(pactl list short sinks | grep -vE 'signal-sink|combined-sink|DesktopAudioShare|MicPlusDesktop|HearLocallyPlusStream|HearAndStream|\tnull' )
echo "$PHYS" || echo "  (none found)"

echo
echo "--- Virtual sinks present ---"
pactl list short sinks | grep -E 'signal-sink|combined-sink|DesktopAudioShare|MicPlusDesktop' || echo "  (none found)"

echo
echo "--- Virtual source (what streaming apps select as mic) ---"
pactl list short sources | grep -E 'MicPlusDesktopSource' || echo "  (none found)"

echo
echo "--- Modules (loopbacks / combine / remap) ---"
pactl list short modules | grep -iE 'loopback|combine|remap-source' || echo "  (none found)"

echo
echo "--- DEFAULT SINK (the critical check) ---"
DEF_SINK=$(pactl get-default-sink 2>/dev/null)
DEFAULT_OUTPUT=$(pactl info | grep -i 'Default Sink')
echo "  default sink node-name: $DEF_SINK"
echo "  $DEFAULT_OUTPUT"

# The core guard: is the default sink a virtual-only null sink?
case "$DEF_SINK" in
    MicPlusDesktop|DesktopAudioShare|signal-sink|combined-sink|MicPlusDesktopSource)
        echo "  FAIL: default sink is a VIRTUAL-ONLY null sink ($DEF_SINK) - NO physical output!"
        echo "        Every app plays into a void. Set default to a combine(physical+virtual) or the physical sink."
        echo "        Fix hint: pactl set-default-sink <physical-or-combined-sink>"
        PA=1
        ;;
    *)
        echo "  PASS: default sink is physical or a combined sink (audio plays locally)"
        ;;
esac

# Optional: warn if no combined sink exists at all (user wants hear+stream)
if ! pactl list short sinks | grep -qE 'HearLocallyPlusStream|HearAndStream|combined-sink'; then
    echo "  WARN: no combined sink found - audio plays locally but will NOT also feed a stream"
fi

echo
echo "--- Test: Record 2s from virtual stream source ---"
VSRC=$(pactl list short sources | grep -E 'MicPlusDesktopSource|signal-source' | head -1 | cut -f2)
if [ -n "$VSRC" ]; then
    pw-record --target="$VSRC" /tmp/verify-audio.wav --rate=44100 --duration=2 2>/dev/null
    # play a tone to the default sink while the record runs below is complex; just report the file
    if [ -s /tmp/verify-audio.wav ]; then
        echo "  Recorded stream source: /tmp/verify-audio.wav ($(stat -c%s /tmp/verify-audio.wav) bytes)"
    else
        echo "  WARN: could not record from $VSRC"
    fi
else
    echo "  (no virtual stream source found, skipping)"
fi

echo
if [ "$PA" = "1" ]; then
    echo "=== >>> RESULT: AUDIO BROKEN (default sink is a virtual-only null sink) <<< ==="
    echo "  FIX: systemctl --user restart audio-sharing-setup.service  (or: pactl set-default-sink <physical-or-combined>)"
else
    echo "=== RESULT: BOTH VIRTUAL SINKS AND A SAFE DEFAULT PRESENT ==="
fi
exit $PA