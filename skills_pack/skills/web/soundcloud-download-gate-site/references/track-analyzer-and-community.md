# Private Track Analyzer + Public Community Hub

Two sibling features added to the AC PE$0 site (acpeso.shop): a PRIVATE per-user
track analyzer with self-learning corrections, and a PUBLIC community tab (beats,
tutorials, chat, connect). Both share the same on-site DSP pipeline. Reuse this
pattern whenever a musician site needs "identify my track" + "share beats" with
clear privacy boundaries.

## DSP pipeline (audio_analyzer.py, pure numpy/scipy/ffmpeg, zero external APIs)

One entry `analyze_bytes(io.BytesIO)` does the whole thing, so the same engine
serves both the private analyzer and community-beat auto-tagging:

- **Decode**: ffmpeg (installed) flattens any upload to mono PCM int16 at 44.1k.
- **BPM**: onset-envelope via spectral flux, then autocorrelation over the onset
  envelope; peak lag in the 70-180 BPM window → BPM. Optionally snap to double/half.
- **Key**: 12-bin chroma (harmonic + percussive split), correlate against
  Krumhansl-Schmuckler major/minor key profiles → best-fit key + confidence.
- **Genre**: heuristic decision tree from tempo, spectral energy, and brightness
  (e.g. fast + high energy → something like trap/dnb; slow + dark → hiphop);
  then biased by learned corrections (below). Genre is inherently the weakest
  guess — treat it as a starting point, not ground truth.

Validated against the site's real beats: BPM and key came back correct for known
tracks; genre was "rough but plausible" and is exactly what the correction loop
improves.

## Self-learning genre memory (genre_learn table)

Every user correction increments a count in `genre_learn` (feature → genre → n).
On analysis, if a learned hint exists for the detected feature and its count beats
the raw heuristic's confidence, bias toward the learned genre. Simple base-rates
table, no ML. This is what turns a static heuristic into something that "gets
smarter" the more people correct it.

## Private-by-design analyzer (/analyze)

Hard privacy requirement from the artist — users' raw tracks must never be
reachable, not even by other users. Implemented as:

1. Upload reads bytes into memory, analyzes, then `os.remove()`s the temp file
   **immediately** (not on some cron cleanup — same request).
2. Only numeric results (bpm, key, genre, plus the UID) are persisted, in an
   `analyses` table keyed to the owning fan.
3. Ownership is enforced server-side: 403 if the requesting fan is not the
   analysis owner AND not admin (`_is_admin_fan`). UI hides rows, but the route
   re-checks anyway — never trust the frontend.
4. Nothing analyzer-related is ever served through a public file route.

## Public community hub (/community) with isolated files

Public posts in four kinds: beat / tutorial / chat / connect. Signed-in users post,
like, and comment; author or admin can delete. Beats attach audio + cover art and
are auto-tagged through the same `analyze_bytes()`.

**Critical isolation rule**: community uploads are stored with a reserved filename
prefix and served ONLY through a dedicated route that whitelists that prefix:

- Files saved as `community-audio-<id>.<ext>` / `community-cover-<id>.<ext>`.
- Served only via `/community-file/{name}` which rejects any name not starting
  with `community-audio-` or `community-cover-`.
- Any other static handler (release covers, lossless, analyzer temps) never sees
  them, and vice-versa — release lossless/private files can never be reached by
  guessing a `/community-file/` name.

This prefix-whitelist pattern is the reusable move: whenever a site mixes public
community uploads with private/protected assets, give the public bucket its own
reserved prefix and a single gated route.

## Rate limiting for user-generated content

New comment path (`/api/item-comment`) enforces `last_comment_time()` — HTTP 429
under a 5-min window with a friendly first-person message ("Easy tiger..."), and
JS surfaces it without breaking the page. Test proves first=200 → immediate
second=429 → only one stored. Same pattern applies to community comments/likes.

## PE$0 voice + tests

All new copy is dash-free (PE$0 rule, see SKILL.md body). New tests added with the
features: analyzer ownership 403, correction learning, file-prefix isolation,
comment rate limit. Keep test count green (88/88) when extending.
