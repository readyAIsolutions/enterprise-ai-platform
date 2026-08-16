---
name: hermes-web-scraper
description: Deep web scraping beyond web_search — HTML parsing, structured data extraction, rate limiting, robots.txt compliance, and JS-site handling. Uses Python stdlib (html.parser, urllib.robotparser) + requests (2.33.0). No beautifulsoup4 needed.
---

# Hermes Web Scraper

Deep web scraping skill for extracting structured data from websites. Uses Python
stdlib where possible — `html.parser`, `urllib.robotparser`, `csv`, `json`, `xml`
are all built in. Only `requests` (2.33.0, pre-installed) is a thin

## Related references

- `references/video-behind-login.md` — watch/transcribe a login-walled video
  (Facebook reel etc.): fish the direct `.mp4` out of the page/embed markup,
  download it anonymously, then faster-whisper the audio. Use when the user
  says "actually watch the whole video" on an auth-gated platform.

## Trigger Conditions

Use this skill when the user asks to:
- Scrape data from a website beyond what `web_search` returns
- Extract tables, lists, or structured content from HTML pages
- Monitor a page for changes over time
- Build a dataset from multiple pages on a site
- Parse XML/RSS/Atom feeds
- Handle pagination or multi-page scraping

## Step 1: Check robots.txt First

Always respect robots.txt before scraping. Use `urllib.robotparser` from stdlib:

```python
from urllib.robotparser import RobotFileParser
rp = RobotFileParser()
rp.set_url("https://example.com/robots.txt")
rp.read()
can_scrape = rp.can_fetch("*", "https://example.com/some/path")
print(f"Allowed: {can_scrape}")
```

If disallowed, STOP and tell the user. Do not scrape disallowed paths. The
`Crawl-delay` directive in robots.txt tells you the minimum delay between
requests — honor it.

## Step 2: Fetch the Page with Proper Headers

Always set a realistic User-Agent. Many sites block default Python/requests UA:

```python
import requests
headers = {
    "User-Agent": "HermesAgent/0.15 (research bot; contact@example.com)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}
resp = requests.get("https://example.com/page", headers=headers, timeout=30)
resp.raise_for_status()
html = resp.text
print(f"Fetched {len(html)} bytes, status {resp.status_code}")
```

Always check `resp.status_code`. Handle 429 (rate limited), 403 (forbidden),
and 503 (server error) with appropriate backoff.

## Step 3: Parse HTML with html.parser (stdlib, no deps)

Python's stdlib `html.parser` works for well-formed HTML. For real-world messy
HTML, prefer installing `beautifulsoup4` (`pip install beautifulsoup4`) —
but stdlib works for clean pages:

```python
from html.parser import HTMLParser

class TableExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_td = False
        self.in_tr = False
        self.current_row = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.in_tr = True
            self.current_row = []
        elif tag in ('td', 'th'):
            self.in_td = True

    def handle_endtag(self, tag):
        if tag == 'tr':
            self.in_tr = False
            if self.current_row:
                self.rows.append(self.current_row)
        elif tag in ('td', 'th'):
            self.in_td = False

    def handle_data(self, data):
        if self.in_td:
            self.current_row.append(data.strip())

extractor = TableExtractor()
extractor.feed(html)
for i, row in enumerate(extractor.rows[:5]):
    print(f"Row {i}: {row}")
```

### Better: Install beautifulsoup4 for messy HTML

If html.parser chokes on malformed HTML (common on real sites):

```bash
pip install beautifulsoup4 lxml
```

Then use the much more robust BeautifulSoup API:

```python
from bs4 import BeautifulSoup
soup = BeautifulSoup(html, 'lxml')  # or 'html.parser'
# Extract all links
links = [(a.get('href'), a.text.strip()) for a in soup.find_all('a') if a.get('href')]
# Extract tables
for table in soup.find_all('table'):
    rows = [[td.text.strip() for td in tr.find_all(['td', 'th'])]
            for tr in table.find_all('tr')]
```

Always try stdlib first and fall back to beautifulsoup4 only if the page is
malformed.

## Step 4: Extract Structured Data

### Pattern A: CSS-selector-like extraction with regex

```python
import re
# Extract all email addresses
emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', html)
# Extract prices
prices = re.findall(r'\$\d+(?:,\d{3})*(?:\.\d{2})?', html)
# Extract dates (ISO format)
dates = re.findall(r'\d{4}-\d{2}-\d{2}', html)
```

### Pattern B: XML / RSS feeds with stdlib xml.etree

```python
import xml.etree.ElementTree as ET
import requests

resp = requests.get("https://example.com/feed.xml", headers=headers)
root = ET.fromstring(resp.text)
for item in root.findall('.//item'):
    title = item.findtext('title', '')
    link = item.findtext('link', '')
    print(f"{title} -> {link}")
```

### Pattern C: JSON APIs directly

```python
resp = requests.get("https://api.example.com/data.json", headers=headers)
data = resp.json()
for item in data.get('items', []):
    print(item.get('name'))
```

## Step 5: Rate Limiting — Be Polite

Always throttle requests to avoid hammering servers:

```python
import time

def polite_fetch(urls, delay=2.0, max_retries=3):
    """Fetch URLs with rate limiting and retry logic."""
    results = []
    for i, url in enumerate(urls):
        for attempt in range(max_retries):
            try:
                resp = requests.get(url, headers=headers, timeout=30)
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get('Retry-After', delay * 5))
                    print(f"Rate limited, sleeping {retry_after}s...")
                    time.sleep(retry_after)
                    continue
                resp.raise_for_status()
                results.append((url, resp.text))
                break
            except requests.RequestException as e:
                print(f"Attempt {attempt+1} failed for {url}: {e}")
                time.sleep(delay * (attempt + 1))  # exponential-ish backoff
        else:
            print(f"FAILED: {url} after {max_retries} attempts")
        time.sleep(delay)
    return results
```

Rule of thumb: 1-3 seconds between requests, more if `Crawl-delay` in robots.txt
says so. Never fire parallel requests to the same domain without explicit
permission.

## Step 6: Handling JavaScript-Heavy Sites

`requests` gets raw HTML — it does NOT execute JavaScript. For dynamic sites:

1. **Check for a hidden API**: Open browser DevTools → Network → XHR/Fetch.
   Often the data comes from a JSON endpoint you can hit directly.

2. **Use the site's sitemap**: `/sitemap.xml` often lists all pages.

3. **Render with a headless browser** (heavy, last resort):
   ```bash
   # Install playwright (one-time)
   pip install playwright
   playwright install chromium
   ```
   ```python
   from playwright.sync_api import sync_playwright
   with sync_playwright() as p:
       browser = p.chromium.launch(headless=True)
       page = browser.new_page()
       page.goto("https://spa-site.example.com")
       page.wait_for_selector(".data-loaded")
       html = page.content()
       browser.close()
   ```

## Step 7: Save Results

```python
import json, csv

# Save as JSON
with open('/tmp/scrape_results.json', 'w') as f:
    json.dump(results, f, indent=2)

# Save as CSV
with open('/tmp/scrape_results.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['url', 'title', 'date'])
    for row in results:
        writer.writerow(row)
```

## Pitfalls

1. **No beautifulsoup4 by default**: This box has `requests` but NOT `beautifulsoup4`.
   Use `html.parser` (stdlib) first. Only `pip install beautifulsoup4 lxml` if
   the page is truly malformed. Check with: `python3 -c "import bs4"`.

2. **Cloudflare / bot protection**: Many sites return 403 or a JS challenge page.
   If `resp.text` contains "Cloudflare" or "checking your browser", the site is
   blocking automated access. Find an alternative data source; don't try to bypass.

3. **Rate limiting with 429**: Always check `Retry-After` header. If absent,
   back off exponentially: 2s → 4s → 8s → 16s.

4. **Character encoding**: Some sites don't declare encoding correctly. Use
   `resp.apparent_encoding` or pass `resp.content` to the parser instead of
   `resp.text`.

5. **Large pages**: Don't print entire HTML to terminal — you'll flood it.
   Always print byte counts, truncated previews, or structured extracts.

6. **robots.txt caching**: `RobotFileParser` doesn't cache by default. If
   scraping many pages from the same domain, parse robots.txt ONCE and reuse.

7. **SSL errors on old sites**: Some sites have expired certs. Use
   `requests.get(url, verify=False)` only as a last resort, and warn the user.

## Verification

Test the full pipeline on a known-safe page:

```bash
# Quick test — scrape Hacker News (robots.txt friendly, static HTML)
python3 -c "
import requests
from html.parser import HTMLParser

class TitleExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.titles = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'span' and attrs.get('class') == 'titleline':
            self.in_title = True
    def handle_endtag(self, tag):
        self.in_title = False
    def handle_data(self, data):
        if self.in_title:
            self.titles.append(data.strip())

resp = requests.get('https://news.ycombinator.com', timeout=15)
ext = TitleExtractor()
ext.feed(resp.text)
for t in ext.titles[:5]:
    print(f'  - {t}')
print(f'OK: {len(ext.titles)} titles extracted')
"
```

Expected output: 30 story titles from the HN front page.
