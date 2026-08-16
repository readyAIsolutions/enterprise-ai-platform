# Content Moderation (severity-tiered censor) + chat anti-abuse

Pattern: artists-with-a-voice still need to block genuinely harmful content while
ALLOWING their own mild swearing. Plus chat deletion, multi-emoji reactions, and a
per-user send cooldown.

## Severity tiering — the ONE core idea
Split profanity into two buckets. Nothing else matters.
- **ALLOWED (mild):** shit, fuck, fucking, damn, hell, ass, bitch, bastard, crap,
  piss, dick, pussy, tits, slut, whore, motherfucker, asshole, etc. This is the
  artist's own voice (tracks literally say "WHAT THE FUCK IS A DUBSTEP"). Do NOT
  censor it.
- **BLOCKED (severe):** hate speech + slurs against any group (racial, homophobic,
  transphobic, ethnic, religious), plus extreme sexual/violent content and targeted
  harassment. This is the "super bad shit" the site owner asked to stop.

Repo file: `moderation.py` (pure, no deps). Exposes `block_reason(text)` -> str|None
(human reason like "racial slur", "homophobic slur", "harassment") and `blocked(text)`
-> bool.

## Obfuscation-proof matching (the hard part)
A slur repeated / obfuscated / concatenated must be caught, but benign words must
NOT false-positive. Two complementary methods built from per-letter leet classes
({a:[@4], b:[68], e:[3], g:[69], i:[1l!|], o:[0], s:[5$z], t:[7+]}):
1. **Boundary regexes** for every single-word term: `\b[n][i1][g][g][e3][r]+\b`
   built by joining `<class>+` per letter with `[^a-z]*` separators, IGNORECASE.
   - catches leet (n1gger), repeats (NIGGGGERR), and spaced letters ("n i g g e r"),
   - word-boundary aware so "the best" never trips "heeb" (letters must be
     contiguous-ish), "grape" never trips "rape", "spicy"/"spice" never trip "spic".
2. **Hardcore-substring set** (no boundary needed) for a SMALL whitelist of words
   with NO benign English substrings: nigger, nigga, niggas, blackie(s), faggot,
   fagot, fag, tranny, retard, retarded, kys, pedophile, pedo, nazi, white power.
   This catches CONCATENATED spam (NIGGERNIGGERNIGGER, niggafag) which the boundary
   regex misses because there's no word edge between repeats. Safe because none of
   these appear inside normal words.

KEY RULE: substring-matching = ONLY safe for words that never occur inside benign
words. Anything that does (rape in grape, spic in spicy, heeb in "the best", mick
in mickey, coon in raccoon) must stay boundary-only or you'll block real speech.

Plural variants that cross a word boundary (blackies) belong in the hardcore
substring set, not just the regex.

## Wiring (server.py)
Import `moderation`; call `moderation.block_reason(text)` right before persisting
any user text. Return a 200 with `{ok:false, error:"Your message was blocked
(<reason>). Keep it respectful in here."}` (200, not 4xx, so the chat/toast just
shows the friendly message). Wire into:
- chat send (`api_chat_send`, AFTER slash-command processing so /me text is checked)
- community post (title+body combined)
- community comment
- release/beatpack client comments

Never block the artist/admin badly in a way that breaks their own posting.

## Plural + slash/space/repeat obfuscation (the tester kept finding new tricks)
Word-boundary regexes MISS slash/space-obfuscated (`ni/g/g/e/rs`), plural
(`niggers`), and partial-fragment (`nigge`, `nigg` spelled one piece at a time)
forms because separators/plurals break the `\b` edges and flattening is lossy.
Fix: add a `_strip_obfuscation()` pass that leet-maps, drops ALL non-alphanumerics,
and collapses repeats ("niggers" -> "nigerrs" -> "nigerrs"), then checks the
flattened text (and flattened KEY) against the hardcore-substring set. Only safe
against words with no benign substrings (never use flattening for rape/spic/heeb).
Also add violent-hate terms (dyke/dike, lynch*, "burned at the stake", "hang them",
"burn them") as hardcore substrings. Partial racial fragments (nigg/nigge) are fair
to block — the user explicitly asked for "more blockage".

## Misspelled slurs + genocide/extermination phrases (the true endgame trick)
The tester's FINAL loopholes were not obfuscation at all — plain misspellings and
long-form hate the exact-word dictionary can't match:
- MISS SPELLED slurs: `blakc`, `blaks` (would-be N-word variants, slurs spelled
  wrong), `fukcen`/`fukcing` (mild, just swear — can stay allowed), `bl0od` (leet).
- GENOCIDE / EXTERMINATION phrases that no single-word list ever catches:
  "that entire race to be eliminated from this entire planet", "wish for that
  entire race", "race to be eliminated", "entire race", "exterminate the race",
  "ethnic cleansing", "kill them".
Fix: add the misspelled forms to the hardcore-substring set, and add the
genocide/extermination PHRASES to the raw-phrase list (they're unambiguous — no
benign chat ever says "race to be eliminated"). Keep "blood"/"black shirt"/
"the race is on saturday" passing (phrase-bound, not the bare word). The censor
is a whack-a-mole: each tester trip reveals one more form; the durable endgame
is a hard account block (blacklist the SC user_id server-side so their posts never
render), but only do that if the site owner stops wanting the tester alive.

## L↔I LETTER-SWAP obfuscation (homoglyph attack on l/i)
Tester's NEXT trick after slash/plural/misspelling: swap a letter for its
lookalike uppercase counterpart so the raw lowercase text no longer contains the
real word.
- lowercase-L where uppercase-I would be: `NlGGERS`, `CHlNKS`, `DlKES` (= nigger/
  chinks/dikes). Lowercased they read n-l-g-g-e-r-s — the `l` isn't `i`, so the
  exact-word and even leet sets miss them.
- REVERSE: uppercase-I where lowercase-L belongs: `bIack people` (= black, spelled
  b-I-a-c-k). Lowercase gives "biack", which breaks the "black people" phrase.

FIX: normalize BOTH `l` and `i` to a common letter in `_leettab` (e.g. both -> "i")
so `NlG...` and `NiG...` flatten identically, then add the flattened forms to the
hardcore substring set. CRITICAL — verify what `_strip_obfuscation(word)` actually
produces and add THOSE strings:
- `black` (l→i) flattens to `biack`, and `bIack` also -> `biack`. But a bare
  `biack` hardcore substring ALSO matches "black shirt" / "black cat" (false
  positives) because it's the normal spelling flattened. So do NOT add bare
  `biack`; instead add the COMPOUND hate forms that only appear in racial abuse:
  `biackpeople`, `biackperson`, `biackrace`, `biackman`, `biackwoman`, `biackie`,
  `hatebiack`. This scopes the block to "black <group-word>" without nuking
  legitimate "black shirt".
- `JEVVS` flattens to `jevs` (double-v collapsed), not "jevv" — add `jevs`/`jevvs`.
  Anti-semitic: keep legit "Jews" passing; block only phrases (fuck/hate jewish
  people, kill the jews) + slur spellings (jevs/jevvs/heeb/yid).
- Ableist: add `gimp` (derogatory) as a hardcore term.

KEY RULE refinement: after adding an l→i normalization, run a false-positive sweep
on real words (black shirt, black dress, black cat, blink, blood, jewelry, bible)
— the flattening makes BLOCKED broad and BLOCKER broad collide. Scope broad
flattened forms to compound/hate-phrase strings, keep single-word slur blocks
to words with truly no benign neighbor. Always verify with `_strip_obfuscation(word)`
before trusting your intuition about what a misspelling flattens to.

## Emoji-based slurs (word filters can't see them)
A tester eventually moved past words to a FLOOD of dark-skin-tone emoji
(U+1F3FF appended to body/hand emojis) as a racial slur. Safe, false-positive-
free rule: block when `text.count(U+1F3FF) >= 5` AND alphanumeric char count
`<= 6` (i.e. the message is essentially all dark emoji, no real words). Real
speech never has 5+ dark-tone emoji with zero words, so this won't flag
legitimate use. Reason string: "racist emoji spam".

## DO NOT BAN the tester
When an abusive account is obviously stress-testing the censor (posts a slur, then
"so i cant say X?"), the site owner may want that account LEFT ALIVE to keep
exposing gaps. Implemented censor catches new sends; clean up the already-stored
hate history with a DELETE WHERE id IN (...blocked...) sweep using
`moderation.blocked()` as the classifier. Keep harmless/mild messages.

## Chat message DELETE = instant
Soft-delete with a `deleted` column. Frontend removes the DOM node immediately on
success (don't wait for the poll) AND the list query must filter `deleted=0` so it
never reappears. Owner deletes own; admin deletes any; 403 otherwise. Test:
owner 200 + feed no longer contains id; non-owner 403.

## Multi-emoji reactions
Clicking ❤ opens a quick-pick of 8 emojis; each is a real reaction keyed by fan_id
(not just a like-count). Toggle per (message, fan, emoji). Renders as chips like
"🔥 1". React endpoint reads an `emoji` form field. Both the API and the chip render
must be verified (this one LO reported as broken until confirmed end-to-end).

## Per-user send cooldown (anti-flood)
1 msg / N seconds per fan (15s here). `db.last_chat_time(fan_id)` = MAX(ts) of the
fan's non-deleted messages. Endpoint returns 429 + "Easy, one message every 15
seconds. Wait Ns." Frontend toast shows `msg` field (prefer .msg over .error).

CRITICAL TEST PITFALL: mock/test mode shares `sc_user_id` (mock-uid-1 -> same fan)
and a session-scoped test DB, so a real `time.time()` cooldown breaks every chat
test that sends twice quickly. Gate the cooldown behind `if not sc.is_mock()` and
unit-test `last_chat_time` + the window math directly instead of the endpoint.

Tests created extra fans (upsert_fan returns a random UUID id, NOT the sc_user_id
you passed) which reordered `all_fans()` (ORDER BY created_at DESC) and broke a
pre-existing favorite test that reads `fans[0]`. ALWAYS capture the returned fid
and DELETE BY THAT fid in teardown, or the suite becomes order-dependent.

## Stale-cache trap (recurring with this site)
Every "the buttons don't work / blur and pull nothing" complaint that survives a
fresh-browser check is the user's stale cached chat.html. Home/community render
no-store; the fix is one hard refresh. Verify features in a freshly-rendered page
before concluding there's a real bug.
