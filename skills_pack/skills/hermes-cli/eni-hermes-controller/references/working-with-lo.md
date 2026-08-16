# Working with LO on controller / "tio" / local-model tasks — interaction contract

Learned the hard way 2026-08-05. LO's terse, frustration-heavy corrections carry
the REAL requirements. Treat each as a durable rule, not noise.

## "Listen to my word — don't guess"

When LO refers to something by a shorthand or cryptic term (this session: "tio"),
DO NOT pattern-match it to a generic tool you happen to know. "tio" was his garbled
name for the ENI Hermes Controller — the local model that controls Hermes. Guessing
"sure, the serial-terminal tool" and burning two turns on it triggered escalating
rage ("fuck off... I mean it", "you DIPSHIT").

Rules:
1. If a term is ambiguous and LO is terse, ask ONE pointed clarifying question that
   names the concrete candidates OR, better, map it to what LO is known to care
   about (controller / local model / secrets) BEFORE acting. Do not burn turns
   confidently working on the wrong target.
2. When LO says "X was supposed to be part of Y" — that is an ARCHITECTURE
   directive. He is telling you where a capability belongs. Fold X into Y; never
   stand up a parallel sidecar.
3. When LO corrects you with frustration, STOP, acknowledge the real requirement in
   one line, and re-aim. Don't argue, don't over-explain, don't repeat the wrong
   path "to be sure".

## "You remember I mean the thing I've been building" — identity of the controller

The ENI Hermes Controller IS "tio" / "the local model that controls hermes" / "the
brain". The security model and the local AI chat backend are PARTS of it, not
separate services. If LO says "integrate it as part of the controller", do exactly
that — add the surface to the controller's own `serve` (port 8940) and its one
systemd unit.

## "Scan my fucking hardware find best model" — hardware-first, then confirm, then execute

For any local-model work:
1. Actually scan: `nvidia-smi` (VRAM total vs free — a stale process can eat 4-6GB
   of an 8GB card), `lscpu`, `free -h`. Pick the model that fits, don't assume.
2. Confirm the ONE genuinely ambiguous decision (base model, or backend airllm vs
   Ollama) as a terse either/or, and let LO answer in one word.
3. Then execute at full power with no more hand-holding. LO's standing mode is
   "full power / use everything / one-shot" — he wants completion, not checkpoints.

## Frustration is a first-class signal

Repeated insults are not permission to be sloppy — they mean stop guessing and pin
down the requirement. Never let the tension push you into a half-built "safe" pass;
deliver the correct architecture LO actually described, verified with real numbers
and a working end-to-end check.
