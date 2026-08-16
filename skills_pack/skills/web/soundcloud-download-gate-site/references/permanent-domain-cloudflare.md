# Migrating the site from an ephemeral tunnel to a permanent domain

Outcome: replace the rotating `trycloudflare.com` quick tunnel with a real domain
(e.g. `acpeso.com`) so the SoundCloud OAuth, Google Gmail-API OAuth and Stripe
webhook callbacks are permanent. This is the "log in / bad gateway / callbacks
keep breaking" fix.

## Why the quick tunnel is wrong long-term
- `~/bin/cloudflared tunnel --no-autoupdate --url http://localhost:8533` gives a
  random `https://<word>-<word>-<word>.trycloudflare.com` that CHANGES on every
  restart. Every rotation invalidates the SC redirect URI, the Google OAuth
  redirect URI and the Stripe callback — all at once.
- Free quick-tunnel edge nodes occasionally 502 ("bad gateway") then recover.

## The two unavoidable dashboard actions (only the user's logins can do these)
1. **Add the domain to Cloudflare** (dash.cloudflare.com → Add a site → Free
   plan). Cloudflare assigns 2 nameservers and copies existing DNS records.
2. **Point the registrar's nameservers at Cloudflare.** For a domain registered
   at a normal registrar this is a routine NS edit. Cloudflare free FULL setup
   requires the NS move — CNAME-only ("CNAME setup") is not available on the
   free plan.

## REGISTRAR-LOCK DEAD-END: a domain REGISTERED WITH Wix cannot move to Cloudflare at all
**Biggest time-sink of this whole migration.** A domain whose **registrar is
Wix.com Ltd.** (i.e. bought WITH Wix, not just connected to a Wix site) CANNOT be
pointed at Cloudflare nameservers. No button, no workaround, and Wix support
flatly refuses:

> "Currently, it is not possible to change or edit name server (NS) records for a
> a domain purchased from Wix. … 2. Transfer your domain away from Wix: If you
> need to use specific name servers like Cloudflare's, you will need to transfer
> your domain to another host."

So once you see Wix's **"NS records are not editable"** grid AND the user's Wix
domain dropdown shows {assign to a site, contact info, manage dns records,
transfer away from wix, transfer to diff wix acc, ...} with NO "Change name
servers" option, **stop hunting for the NS control — it does not exist.** Wix
holds a Wix-bought domain's DNS hostage. Recovering it requires **transferring
the domain away** (below). Do NOT send the user back into Wix looking for a
button a third time.

**Distinguish "registered with Wix" vs "connected to Wix":**
- **Registrar = Wix.com Ltd.** (confirm via RDAP `entities[]` w/ `roles:
  ["registrar"]`, `fn: Wix.com Ltd.`, handle `3817`). NS is locked → only a
  transfer fixes it.
- **Domain registered elsewhere, only DNS/DNS-records managed at Wix** → the
  real NS change lives at the actual registrar, not Wix. (This is the case the
  old "Wix → My Domains → Manage → Nameservers" note assumed — rare for the
  user's Wix-bought domains.)

**Wix's offered alternatives, and why they don't help here:**
1. "Point to an external site via A/CNAME records" — only works if the site is
   at a **fixed public IP reachable from the internet**. Behind a home NAT with a
   **rotating** IP (see NAT check below), an A-record pointing at the box is
   fragile/wrong — exactly why we use tunnels.
2. "Transfer away from Wix" — the actual path (below).

## CRITICAL: Cloudflare's "waiting for propagation" screen is GENERIC — verify yourself
Cloudflare shows **"Waiting for your registrar to propagate your new nameservers
… 1-2 hours / up to 24 hours"** for *every* newly-added domain, even when the
registrar nameservers were NEVER changed. Seeing that screen is NOT proof the NS
move happened. The user pasting it back is often a sign the registrar step got
stuck or skipped. Independently check the REAL state at the registry + resolvers:

```bash
# 1) Public resolvers — still Wix => the move did NOT happen
dig @8.8.8.8 acpeso.com NS +short      # expect: ethan/gina.ns.cloudflare.com
dig @1.1.1.1 acpeso.com NS +short      # another resolver to confirm

# 2) Registry (authoritative, survives resolver cache) — Verisign RDAP for .com
curl -s https://rdap.verisign.com/com/v1/domain/acpeso.com | python3 -m json.tool
# look at "nameservers"[].ldhName and "entities"[0].handle/vcardArray fn (registrar)
```
If resolvers AND registry still show `NS1x/NS1y.wixdns.net` (or
`ns1x.wixdns.net`), the registrar-side change did not land — do not proceed with
the tunnel/flip until it does. RDAP also names the true registrar (the `fn`
under `roles: ["registrar"]`, e.g. `Wix.com Ltd.`, handle 3817), so you know
which dashboard actually holds the NS change.

## Sequencing: "Without DNS records, Cloudflare is unable to activate your site" is NOT a records task
Right after adding a domain, Cloudflare's dashboard onboarding prints
**"Without DNS records, Cloudflare is unable to activate your site. It's best if
you set up your DNS records now."** This is a GENERIC message that fires for every
new zone; it does NOT mean you must add records first. **Activation comes from the
registrar NS move (ethan/gina visible at the registrar), NOT from adding records.**
Adding records while the zone is `pending` is harmless but they just hang until NS
lands. Correct order for a domain you control:
1. Point the registrar's nameservers at the 2 Cloudflare-assigned NS (that is the
   actual activation step).
2. Only then does `pending → active` and the warning clear.

KEY discovery: you can build the WHOLE Cloudflare side **while the zone is still
`pending`** — `cloudflared tunnel login` (cert.pem), `tunnel create`, writing
`config.yml`, and even `tunnel route dns` all succeed pre-activation. Only actual
public traffic waits on the NS propagation completing. So pre-stage everything,
then the moment `pending → active` you just start the tunnel / flip the app.

## Check NS with DNS-over-HTTPS (public UDP resolvers may be blocked)
`dig @8.8.8.8@ / @1.1.1.1` can return **connection refused** on boxes where outbound
UDP 53 to public resolvers is filtered. Fall back to DoH (JSON), which needs only
HTTPS:
```bash
# Cloudflare DoH + Google DoH
curl -s -H 'accept: application/dns-json' \
  "https://dns.google/resolve?name=acpeso.shop&type=NS"
curl -s -H 'accept: application/dns-json' \
  "https://cloudflare-dns.com/dns-query?name=acpeso.shop&type=NS"
```
## NXDOMAIN (Status 3) = domain not registered / not delegated — distinct from `pending`
When checking NS of a brand-new domain, if the DoH answer has `"Status":3` and only
the TLD's own SOA/registry NS (e.g. `.shop` → `a.gmoregistry.net`), the domain is
**not yet registered or not yet delegated** at the registry — it is NOT the same as
a `pending` Cloudflare zone. A just-completed registration can take ~15–60 min to
appear in public DNS. Distinguish the two states before concluding the user's
purchase failed: a real registry delegation returns the domain's actual NS
(ethan/gina), not the TLD's SOA.

## Namecheap Custom DNS — the exact UI path (registrar never locks NS)
Namecheap gives full NS control (unlike Wix). Exact steps:
1. **Domain List** (top-left menu) → find the domain → **Manage** (right edge).
2. In the **left column**, the **NAMESERVERS** box shows `BasicDNS` / Namecheap
   defaults.
3. Switch the dropdown to **Custom DNS** → two fields appear.
4. Enter the 2 Cloudflare NS (delete any defaults), then click the green
   **checkmark / save** in that box → "Saved successfully" toast.
5. Zone flips pending → active within minutes. Do NOT touch "Advanced DNS" for the
   NS change (that box is for individual records, which the agent adds via the CF
   API after the tunnel exists).

## Pitfall: "NS records are not editable" in Wix means CHECK WHO THE REGISTRAR IS
When DNS is managed at/for a Wix-hosted domain, Wix's **"Manage DNS Records"**
grid shows the `nsXX.wixdns.net` rows as **"NS records are not editable"** —
that is normal and NOT the place to change nameservers either way. Before sending
the user hunting: use RDAP to confirm the registrar.
- **Registrar = Wix.com Ltd.** → the "not editable" lock is permanent; there is
  NO "Change name servers" control anywhere and support refuses. The ONLY way to
  use Cloudflare NS is to **transfer the domain away** (see
  "TRANSFER" section above). Do not keep fishing in Wix's UI.
- **Registrar = someone else, only DNS is at Wix** → the real NS change lives at
  the actual registrar's dashboard (just like a normally-registered domain);
  go there.

The touchstone "you see a 'Change name servers' button" from older notes only
applies to registrars that allow editing. Wix-registered domains never show it.

The two DNS checks (below) are the ground truth either way: re-run
`dig @8.8.8.8` + RDAP after any change, and only proceed when both show the
Cloudflare nameservers.

## FASTEST FIX when the registrar locks NS: buy a NEW domain, don't transfer
If the user is blocked on a registrar-locked domain (Wix) AND doesn't want to wait
~5–7 days for a transfer, the fastest permanent path the user will accept is to
**register a brand-new domain at a registrar with full NS control** (Namecheap)
and point THAT at Cloudflare. This is what happened for AC PE$0: Wix refused NS
changes on `acpeso.com`, so the user said **"fuck it to wix"** and registered
**`acpeso.shop` at Namecheap** instead. Site/storefront domains → .shop is a good
natural fit (.store/.shop read as commerce). No transfer wait, no lock, live in
minutes. Flow:
1. Register the new domain at Namecheap (the API token can create the zone in
   Cloudflare even before/while the purchase completes, so create it in parallel).
2. Cloudflare **Add a site** → new domain → note the 2 assigned nameservers.
3. Namecheap → Domain List → **Manage → Nameservers → Custom DNS** → enter the 2
   Cloudflare nameservers. (Namecheap NEVER locks NS, unlike Wix.)
4. Zone flips pending → active within minutes. Then named tunnel + flip below.
Keep the `flip_to_acpeso.py` DOMAIN constant as the sole thing to change when the
domain moves — repoint it (`acpeso.com` → `acpeso.shop`) so the flip has zero
rework, and mirror the same hostname change in the tunnel `config.yml` ingress
(`{domain}` + `www.{domain}`).

## TRANSFER the domain to Cloudflare Registrar (the fix for a Wix-bought domain)
Cloudflare Registrar is the natural home because the zone is already created in
Cloudflare; after the transfer completes, **Cloudflare is both registrar AND
DNS**, so it publishes ethan/gina itself, the zone flips pending → active, and
the named tunnel + flip below all just work. ~$10/yr renewal, ~5–7 days,
mostly automatic.
1. In Wix: **"Transfer away from Wix"** → get the **EPP/auth code**, and confirm
   release. (Make sure the domain is not within ~60 days of its last
   transfer/registration.)
2. At Cloudflare: **Domain Registration → Transfer → acpeso.com** → pay (~$10.80)
   → enter the auth code. (An agent with the CF API key can drive this side.)
3. Wix releases → transfer completes (auto) → Cloudflare NS → zone active.
4. Then run the named-tunnel + flip recipe below.
During the ~5–7 days, keep the existing quick tunnel running exactly as-is — no
regression; the site stays up at its rotating hostname until the transfer lands.

## Pitfall: "point it at my box with an A record" only works if the box is directly exposed
If the user asks "can't we just point the A record at our server?", check whether
the public IP is on the box or a router/NAT first:
```bash
ip -4 addr show | grep inet                     # local NIC IPs (192.168.x.x = NATed)
curl -s https://api.ipify.org                   # public egress IP
# does the public IP appear on a local NIC? if NOT, the box is behind NAT/NAT-router
```
Behind a home router with a **rotating** public IP, direct A-record hosting needs
port-forwarding + dynamic-DNS + HTTPS termination — fragile, don't recommend.
That's the very reason the site uses a tunnel. Only pursue A-record hosting if
the box has a static reachable public IP directly on a NIC.

## DON'T fight a limited API token — use `cloudflared tunnel login`
The light API token in `.env` may be read-only for this purpose and you will
burn time. Symptoms observed with a scoped token:
- `POST /zones` → `"Requires permission com.cloudflare.api.account.zone.create"`
- `POST /accounts/<id>/cfd_tunnel` → `{"code":10000,"message":"Authentication error"}`
- but `GET /accounts`, `GET /zones?name=<domain>` succeed (read works).

The standard path grants the needed perms WITH the user's browser instead:
`cloudflared tunnel login` opens a Cloudflare OAuth in the browser; once the user
clicks Allow it writes `~/.cloudflared/cert.pem` scoped to their account. Then
you (the agent) can create/route/run the tunnel without needing a privileged API
token.

## Full recipe
```bash
CF="$HOME/bin/cloudflared"; CDIR="$HOME/.cloudflared"; mkdir -p "$CDIR"; cd "$CDIR"
"$CF" tunnel login                 # browser auth -> cert.pem (user clicks Allow)
"$CF" tunnel create acpeso         # creates named tunnel, writes <tunnelid>.json
TID=$("$CF" tunnel list --output json | python3 -c "import sys,json;print(json.load(sys.stdin)[-1]['id'])")

cat > config.yml                  # ingress to the LOCAL app
#   tunnel: $TID
#   credentials-file: $CDIR/$TID.json
#   ingress:
#     - hostname: acpeso.com
#       service: http://localhost:8533
#     - hostname: www.acpeso.com
#       service: http://localhost:8533
#     - service: http_status:404

"$CF" tunnel route dns acpeso acpeso.com     # CNAME acpeso.com -> <tid>.cfargotunnel.com
"$CF" tunnel route dns acpeso www.acpeso.com
"$CF" tunnel run acpeso             # keep the old quick tunnel running until confirmed
```
Do NOT stop the existing quick tunnel until `curl https://acpeso.com` returns the
site — the user should never see a completely down site.

## Flip the app URLs ONLY after the domain actually serves
The callback config is the last mile and must not change a second early (it
breaks login). Once `https://acpeso.com` serves the app, update all of these to
the permanent domain at the same time — a `flip_to_acpeso.py` style helper that
rewrites `.env` lines AND `db` settings (`site_url`, `sc_redirect_uri`,
`gc_redirect_uri`) with a `--dry-run` is the safe pattern:
- `SITE_URL` / `site_url` → `https://acpeso.com`
- `SC_REDIRECT_URI` → `https://acpeso.com/callback`
- `GC_REDIRECT_URI` → `https://acpeso.com/gc-callback`
Then restart the server, and update these in their own dashboards (user action):
- Stripe webhook → `https://acpeso.com/stripe/webhook`
- SoundCloud app Redirect URI → `https://acpeso.com/callback`
- Google Cloud OAuth Authorized redirect URI → `https://acpeso.com/gc-callback`

## Pitfalls
- **Stale LOCAL DNS cache outlives propagation — the #1 "it's still broken" false alarm.** After the registrar NS move lands and DoH/Cloudflare show the domain resolving, `curl https://<bare-domain>` from the SAME box can return `HTTP 000` / `curl: (6) Could not resolve host` because the box's local resolver (`systemd-resolved`) cached the pre-propagation NXDOMAIN. Symptoms that give it away: `https://www.<domain>` returns 200 but the bare apex returns 000, while a DoH query (dns.google / cloudflare-dns.com) resolves the apex to Cloudflare edge IPs. **Prove the site is actually fine by bypassing the local cache** before declaring a problem:
  ```bash
  IP=188.114.96.10   # an edge IP from the DoH A-record answer
  curl -s -o /dev/null -w "%{http_code}\n" --resolve acpeso.shop:443:$IP https://acpeso.shop
  ```
  Then tell the user to flush their cache: `sudo systemd-resolve --flush-caches` (or restart browser / wait). Do NOT start re-starting the server or tunnel over a stale-cache 000.

- **`cloudflared tunnel login` can die with a bare `error="Failed to fetch resource"` / empty URL first try.** This is transient — just rerun it (each run prints a NEW `https://dash.cloudflare.com/argotunnel?...` URL for the user to open + Allow). Keep testing for `~/.cloudflared/cert.pem` / the log line `You have successfully logged in` as the real completion signal, not just that a URL was printed.

- **Shell-quote a `$` inside a directory path.** `~/Desktop/ac pe$0` — an unquoted `cd /home/hunter/Desktop/ac pe$0` makes bash eat the `$0` (`cd: .../ac pe/usr/bin/bash: No such file`). Always `cd '/home/hunter/Desktop/ac pe$0'` (single quotes).

- OAuth/Stripe dashboards cache the old redirect until edited — changing only the
  app config (or only one dashboard) leaves login broken. Move them together.
- Verify with `curl -I https://acpeso.com` (expect 200) and
  `curl -I https://acpeso.com/callback` (SC/Google may 400 on the bare path —
  that's fine, we only need the hostname to route) before telling the user it's
  live. Do NOT flip before this passes.
- The site is served from the same local server behind the tunnel — nothing is
  "uploaded"; the domain just points to it. If the user says a key is missing on
  the public site, suspect login, not config.
