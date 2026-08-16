# Research technique — when the web / delegate tool hangs

## Problem observed (2026 session)
`delegate_task` with the `web` toolset was invoked 3× to research Crown-land fishing. Every run hung: one interrupted after 9s, one returned only a self-narration with no tool calls, one timed out at 600s. The subagent stalled on browse/network calls and never produced usable results.

## Fix — do the research yourself from terminal
You have a Linux terminal with network access. Prefer **direct `curl` of authoritative pages + Python HTML parsing** over search-engine scraping (Bing/Mojeek HTML endpoints returned blocked/empty bodies; DuckDuckGo HTML returned nothing).

### Pattern that worked
```bash
# 1) Probe candidate official URLs (gov .ca pages); 200 + large size = good
for u in "https://www.alberta.ca/public-lands-camping-pass" \
         "https://www.alberta.ca/camping-on-public-land" ; do
  code=$(curl -sL --max-time 20 -o /tmp/p.html -w "%{http_code}" -A "Mozilla/5.0" "$u")
  echo "$code $(wc -c </tmp/p.html) $u"
done

# 2) Strip markup and print the readable body
python3 -c "
import re,html
t=open('/tmp/p.html').read()
t=re.sub(r'<script.*?</script>','',t,flags=re.S)
t=re.sub(r'<style.*?</style>','',t,flags=re.S)
t=re.sub(r'<[^>]+>',' ',t)
t=html.unescape(t); t=re.sub(r'\s+',' ',t)
i=t.lower().find('skip to content')
print(t[i:i+2500] if i>0 else t[:2500])
"
```
- Government text pages render server-side, so `curl` + tag-strip gets the real content (no JS needed).
- For search-result snippets, Bing's `b_algo` / `h2>a` patterns were unreliable; go straight to known official URLs instead of scraping a SERP.
- Provincial sites reorganize constantly → expect 404s. Try sibling slugs / parent sections; content often still serves.

### When to use this
- delegate_task web hangs/times out (seen repeatedly here).
- You need authoritative facts (regs, dates, fees) from a .gov/.ca site.
- Search engines rate-limit or block automated requests.

### Do NOT harden this into "web tool is broken"
The delegate/web tool may work fine in other sessions. Frame it as a *fallback*: "if the web tool hangs, drop to terminal curl." Retry the delegate once; only fall back after it fails.
