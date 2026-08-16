# Community-Chat "Free Stuff" Features (soundboard / name effects / fun cmds / multi-emoji)

Pattern for adding lightweight engagement/chat features to the AC PE$0 (or any SQLite-backed
single-admin chat) without shoving in a heavy economy. Ported from a reference `nexus.html`
but rebuilt on OUR backend; kept the "free" features and deliberately left out the
"not-free" ones (coin-economy casino, DM store). 108/108 tests after adding 5 new ones.

## Free features (all client JS + SQLite back-end, no external uploads/storage)

1. **Soundboard** — a "Sounds" pill in the chat top bar opens a 9-sound synth board
   (Airhorn, Ba-dum-tss, Boom, Sparkle, Wrong, Correct, Spooky, Robot, Win).
   ALL generated in-browser via **Web Audio oscillators/envelopes** — zero uploads, zero
   storage, free and instant. Don't ship audio files; synthesize them.
2. **Name effects** — an "Effect" pill with a picker (glow, rainbow, glitch, neon, fire,
   ice, pulse, wobble, float, blink, gradient, shimmer) + live preview. The chosen effect
   class is stored on the user profile and applied to the name in chat messages, the online
   sidebar, and the me-card. Profile already had an `effect` field, so it dropped straight in.
3. **Fun slash commands** — `/roll [max]`, `/flip`, `/8ball [question]`, `/shrug` —
   handled SERVER-SIDE (never trust client), and each is added to the `/help` menu.
4. **Multi-emoji reactions** — clicking the ❤ on a message opens an 8-emoji quick-pick
   (❤😀😂🔥💀👍🎉😮); clicking an existing reaction toggles that emoji. A message can carry
   multiple DIFFERENT emojis now, not just a single heart.

## Deliberately deferred ("not-free" parts of the reference)
- Casino (blackjack/crash/dice/plinko/slots) — needs a real coin economy backend.
- DMs — needs a private messaging store.
Both are clean follow-ups; only build if the user asks.

## Verification discipline
- Re-run the FULL test suite — this one ended at 108/108 pass (incl. 5 new: fun commands,
  multi-emoji, effect persistence, help list).
- Node-validate inline JS that gets injected into rendered pages.
- Confirm each new element is actually present in the rendered page (snapshot).
- Restart the server and confirm it's live on the site (acpeso.shop) before declaring done.
- Log as an Upgrade #N in STATUS_ACPE$0.md with the running count.
