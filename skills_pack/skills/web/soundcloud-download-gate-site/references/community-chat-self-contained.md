# Community chat: stay self-contained, never port third-party keys

## User rule (non-negotiable)
When LO hands over a reference/found HTML file (e.g. a `nexus.html` Discord-style chat) and
says "port the cool stuff", ONLY port the UI/UX ideas. Do NOT carry over any third-party API
keys, credits, or service dependencies ("the original html had api keys and stuff for the
community prompt those are NOT ours dont use them"). Anything that would call a host we don't
control, or embed a credential that isn't the site's own, must be rebuilt self-hosted or dropped.

What "ours" means on this project: all chat identity = real SoundCloud login; all data on our
own SQLite; all generated media local (client-side or on our server). Nothing pings another
party's API except SoundCloud itself.

## Audit before you declare clean
`grep -rniE "..." ` across .py/.html/.js/.css for secrets: `sk-`/AI keys, `AIza...`,
`pk_(live|test)_`, `api[_-]?key`, `bearer `, third-party hosts (openai/anthropic/fal/stability/
sendgrid/twilio/firebase/googleapis/jsdelivr/unpkg). Plus list every external `https://` URL in
the template and whitelist only our domain + SoundCloud. A keyless third-party URL is STILL a
foreign dep (see avatar below) and should be removed when the user asks for zero external deps.

## Technique: local SVG data-URL avatar instead of a third-party avatar service
Reference HTML commonly uses `https://api.dicebear.com/...` for user avatars. It's a free
keyless service, but it's still a request to a host you don't control and fits the user's
"not ours" rule. Replace with a fully local generator:

```js
function localAvatar(seed){
  var h=0,s=seed||'';
  for(var i=0;i<s.length;i++){h=(h*31+s.charCodeAt(i))>>>0;}
  var hue=h%360, ch=(s||'?').charAt(0).toUpperCase();
  var svg='<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
    +'<rect width="96" height="96" rx="24" fill="hsl('+hue+',55%,26%)"/>'
    +'<text x="48" y="63" font-family="Anton,Arial,sans-serif" font-size="44" fill="#fff" text-anchor="middle">'+ch+'</text></svg>';
  return 'data:image/svg+xml;utf8,'+encodeURIComponent(svg);
}
```
Deterministic hue from a hash of the seed id + first initial. Use `localAvatar(myId)` for the
initial default and `localAvatar(myId+Date.now())` for a "random avatar" button. Real user
picture (SoundCloud `sc_avatar`) still takes priority when present.

## Pitfall: node --check on templates that mix Jinja + JS
`node --check` will choke on `{{ vars }}` / `{% ... %}` / `{# ... #}` inside inline `<script>`.
Strip them before validating with Python:

```python
import re
h=open('templates/chat.html').read()
h=re.sub(r'\{\{.*?\}\}', '0', h, flags=re.S)          # expr -> dummy
h=re.sub(r'\{%-?\s*.*?-?%\}', '', h, flags=re.S)      # stmt -> drop
h=re.sub(r'\{#.*?#\}', '', h, flags=re.S)             # comment -> drop
open('/tmp/chat_inline_clean.js','w').write(re.search(r'<script>(.*?)</script>', h, re.S).group(1))
```
Then `node --check /tmp/chat_inline_clean.js`. This isolates real JS syntax errors from template tags.

## Deployment note
A template change renders live with no restart because `_render()` sends `Cache-Control:
no-store` on dynamic HTML (see main skill). Still restart the systemd service as the go-live
habit and re-run the full test suite (`python3 -m pytest tests/test_site.py -q`) after any
chat/template edit.
