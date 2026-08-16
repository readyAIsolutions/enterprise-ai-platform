# Gather Hints — plain-language "where to get it" for the lesson "What to gather" block

The swarm's `gather_block(G, M)` expands each gear/material item into a `<li>` with a
hint. Map is keyword->hint; `gather_line(item)` matches by substring. Add more keys as
new clusters appear.

```
scale            : a digital kitchen scale that reads to 0.1 g — any grocery/drugstore 'precision scale' works
gloves           : nitrile gloves (blue/black disposable), not latex — box at any hardware store
goggles          : splash goggles that seal around eyes, not safety glasses with gaps
beaker           : glass beaker or clean glass jar — science kit or cheap
nitric acid      : concentrated nitric acid — restricted; chemical supply / lab surplus; primary hazard
sulfuric acid    : concentrated sulfuric acid — drain cleaner / battery acid grade (purify); burns skin
erythritol       : zero-calorie sugar substitute 'Swerve' / generic at any grocery
fuel oil         : #2 diesel from pump or can of lamp oil
ammonium nitrate : prilled fertilizer 34-0-0 or stump remover — source of nitrate
aluminium powder : atomized Al flake from pyro supplier / flashed Al from pottery supplier
ferric oxide     : red iron oxide 'rouge' polish / blacksmith scale ground fine
copper           : copper pipe/sheet from hardware store — liner metal
rtl-sdr          : RTL-SDR v3 dongle (~$30) online — USB SDR receiver
antenna          : wire dipole or discone — cut to band, or buy wideband
proxmark         : Proxmark3 (clone ~$40) for RFID
veracrypt        : free Veracrypt — official site, clean machine
monero           : Monero wallet — getmonero.org, air-gapped machine
caliper          : digital caliper (~$15) hardware store — measures mm
micron filter    : box-fan + furnace HEPA panel taped to intake — make-shift clean bench
petri dish       : plastic petri dishes — science supply / school lab
agar             : agar-agar powder — Asian grocery / lab supply
borosilicate     : Pyrex borosilicate, not soda-lime — lab supply
ph meter         : ~$10 pH pen — hydroponics shop
salt             : non-iodised / pickling salt — grocery
mason jar        : standard canning jar w/ two-piece lid — supermarket
stepper motor    : NEMA 17 — 3D-printer parts / electronics surplus
arduino          : Arduino Nano clone (~$5) — electronics seller
filament         : PLA/ABS spool — printer supplier
torch            : propane torch — hardware store
compass          : baseplate orienteering compass (~$15) — outdoor store
mylar bag        : mylar food-storage bag — prepper supplier
```
Fallback line (no keyword match): "gather this before you start; if you do not recognise
it, look it up by name and buy the plain version, not a 'kit'."
