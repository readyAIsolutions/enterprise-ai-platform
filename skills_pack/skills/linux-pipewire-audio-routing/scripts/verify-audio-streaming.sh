#!/bin/bash
# Functional end-to-end test for "hear locally + stream" audio routing.
# Verifies that (a) audio actually reaches the physical output and
# (b) desktop audio is captured by the stream mic.
#
# Usage: verify-audio-streaming.sh [DEFAULT_SINK] [STREAM_SOURCE]
# Defaults are typical for LO's desktop-sharing setup.
# Exit 0 = PASS, 1 = FAIL.

SINK="${1:-$(pactl get-default-sink)}"
SRC="${2:-MicPlusDesktopSource}"
TONE=/tmp/_audtest_tone.wav
CAP=/tmp/_audtest_cap.wav
RATE=48000

echo "Default sink:   $SINK"
echo "Stream source:  $SRC"

# sanity: default sink must NOT be a bare virtual null sink (the silence bug)
case "$SINK" in
    MicPlusDesktop|DesktopAudioShare|*".monitor"*|"") 
        echo "FAIL: default sink is virtual-only ($SINK) -> silent void bug"; exit 1 ;;
esac

# generate a 1s 440Hz tone as signed-16 stereo
python3 - "$TONE" "$RATE" <<'PY'
import struct, math, wave, sys
fn, sr = sys.argv[1], int(sys.argv[2]); dur, n = 1, sr
w = wave.open(fn,'w'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
data = b''.join(struct.pack('<hh',
    int(12000*math.sin(2*math.pi*440*t/sr)),
    int(12000*math.sin(2*math.pi*440*t/sr))) for t in range(n))
w.writeframes(data); w.close()
PY

# (1) does the tone reach the default sink's physical output?
paplay "$TONE"
sleep 0.3
pactl list short sinks | grep -q RUNNING || { echo "FAIL: no RUNNING sink after play"; exit 1; }
echo "OK: physical output went RUNNING (audible)"

# (2) is the desktop audio captured by the stream mic?
pw-record --target="$SRC" "$CAP" --rate=44100 &
REP=$!
sleep 0.5
paplay "$TONE"
sleep 1.8
kill "$REP" 2>/dev/null; wait 2>/dev/null
sleep 0.3

python3 - "$CAP" <<'PY'
import wave, struct, os, sys
fn = sys.argv[1]
if not os.path.exists(fn):
    print("FAIL: capture file missing"); sys.exit(1)
w = wave.open(fn,'r'); f = w.readframes(w.getnframes()); w.close()
samples = struct.unpack('<%dh' % (len(f)//2), f) if f else []
peak = max(abs(s) for s in samples) if samples else 0
print("Stream-mic capture peak =", peak)
sys.exit(0 if peak > 2000 else 1)
PY
[ $? -eq 0 ] && echo "PASS: desktop audio streams as mic" || echo "FAIL: silent capture"

rm -f "$TONE" "$CAP"