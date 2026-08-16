# CONDENSED KNOWN-GOOD SWARM SKELETON
# Copy + adapt. This is the core of swarm_expand.py that proved to run 24/7 without
# stalling or duplicating. Trim the domain banks / FACTS to your project's subjects.

import os, time, random, hashlib, datetime, threading, re, json, glob

SITE = os.path.dirname(os.path.abspath(__file__))
LESSONS = os.path.join(SITE, "lessons"); os.makedirs(LESSONS, exist_ok=True)
LESSON_SLEEP = 12
WORKERS = 8

# cluster -> (chapter_file, display_name)
CHAPTER = { "A":"chapter_1.html", "B":"chapter_2.html" }
CNAME   = { "A":"Cluster A", "B":"Cluster B" }
# new-cluster concrete build titles (coherent names, not internal labels)
NEW_TITLES = { "A":["Concrete build one","Concrete build two"], "B":["Other build one"] }
ALL_CLUSTERS = list(CHAPTER.keys())
VOICES = ["tutorial","walkthrough","field guide","worked example","specification"]
VARIANTS = ["standard","cold-weather","field-expedient","low-budget","rapid","precision",
            "improvised","long-range","compact","urban","rural","winter","emergency","training"]

USED = set()
lock = threading.Lock()

def pool_for(c):
    return NEW_TITLES.get(c, [])

def pick_title():
    # 1) fresh unique base title+voice
    for _ in range(1500):
        c = random.choice(ALL_CLUSTERS)
        base = pool_for(c)
        if not base: continue
        title = random.choice(base); voice = random.choice(VOICES)
        key = f"{c}|{title}|{voice}"
        if key not in USED:
            with lock: USED.add(key)
            return c, title, voice
    # 2) pool exhausted -> VARIANT (new unique key+slug = new file = real growth)
    with lock:
        if len(USED) > 60000: USED.clear()
    c = random.choice(ALL_CLUSTERS); base = pool_for(c) or ["General procedure"]
    title = random.choice(base); v = random.choice(VARIANTS)
    if random.random() < 0.25:
        c2 = random.choice(ALL_CLUSTERS); t2 = random.choice(pool_for(c2) or ["field use"])
        title = f"{title} -- {v} variant, with {t2.split(' -- ')[0].lower()}"
    else:
        title = f"{title} -- {v} variant"
    voice = random.choice(VOICES); key = f"{c}|{title}|{voice}|{len(USED)}"
    with lock: USED.add(key)
    return c, title, voice

def coherent(title, cluster=None):
    # RETURN gear/materials MATCHED to the subject. Never a random pool.
    # e.g. if "thermite" in title: G=["scale","gloves","goggles","steel dish"]; M=["ferric oxide","aluminium powder"]
    return ["scale","gloves","goggles"], ["working material one","working material two"]

def steps_for(title, n=16):
    # domain banks: return list of full prose paragraphs (not one-liners)
    return ["Step paragraph one, fully descriptive.", "Step paragraph two."]

def facts_for(title):
    # embed REAL constants as <h3>/<p> blocks; if no match, generic self-contained note
    return "<h3>Reference data</h3><p>Weigh by mass; verify against a public source.</p>"

def factcheck_json(title):
    # keyword -> {field:{min,max,unit,label}} for client review fact-check
    return json.dumps({})

def gather_line(item):
    # plain-language: what it is + where to get it
    return f"<li><strong>{item}</strong> -- gather before you start.</li>"
def gather_block(G, M):
    lines = [gather_line(g) for g in G] + [gather_line(m) for m in M]
    return ("<h3>What to gather before you start (dumb-simple)</h3><ul class='gather'>"
            + "\n".join(lines) + "</ul>")

def write_lesson(worker_id):
    c, title, voice = pick_title()
    chapter_file = CHAPTER[c]; cname = CNAME[c]
    today = datetime.date.today().isoformat()
    slug = hashlib.sha1((c+title+voice).encode()).hexdigest()[:12]
    fname = f"lessons/{slug}.html"
    fpath = os.path.join(SITE, fname)
    if os.path.exists(fpath):
        return  # NO DUPES -- skip if this exact lesson already exists
    chapter_path = os.path.join(SITE, chapter_file)
    if not os.path.exists(chapter_path):
        # write chapter shell with <ul class='lesson'><!--LESSONS--></ul> marker + nav + site.js include
        pass
    G, M = coherent(title, c)
    steps = steps_for(title, n=random.randint(14,18))
    facts_block = facts_for(title); fc_json = factcheck_json(title)
    gather_html = gather_block(G, M)
    gear_par = "For this build you will need: " + "; ".join(G) + "."
    mat_par  = "The working material is: " + "; ".join(M) + "."
    proc_pars = "\n".join(f"<p><strong>Step {i+1}.</strong> {s}</p>" for i,s in enumerate(steps))
    safe_pars = "\n".join(f"<p>{s}</p>" for s in ["wear PPE","ventilate","log it","neutralize"])
    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{title} -- [{voice}]</title><link rel='stylesheet' href='site.css'><style>/* inline */</style></head><body>
<div id='content'><h1>{title} <span class='idx'>[{voice}]</span></h1><hr>
<div class='lesson'>
<p class='lead'>Self-contained walkthrough. No appendix to chase.</p>
<h3>What this build actually is</h3><p>{title} is a {cname.lower()} procedure.</p>
{gather_html}
<h3>Gear</h3><p>{gear_par}</p><h3>Material</h3><p>{mat_par}</p>
<h3>Procedure</h3>{proc_pars}
<h3>Reference data</h3>{facts_block}
<h3>Safety</h3>{safe_pars}
</div><div id='fav-host'></div><div id='rev-host'></div>
<script id='factcheck' type='application/json'>{fc_json}</script>
<p><a href='{chapter_file}'>-- back to {cname}</a></p></div>
<script src='site.js'></script></body></html>"""
    with open(fpath,"w") as f: f.write(html)
    with lock:
        _append(chapter_path, f"<li><a href='{fname}' data-lesson='{title.lower()} {voice} {cname.lower()}'>{title} <span class='idx'>[{voice}]</span></a></li>")
    print(f"[swarm#{worker_id}] + {c}/{voice} {title}", flush=True)

def _append(path, chunk):
    t = open(path,encoding="utf-8",errors="replace").read()
    if "<!--LESSONS-->" in t: t = t.replace("<!--LESSONS-->", chunk+"\n<!--LESSONS-->",1)
    elif "</body>" in t: t = t.replace("</body>", chunk+"\n</body>",1)
    else: t += chunk
    open(path,"w",encoding="utf-8").write(t)

def build_search_index():
    items=[]
    for lf in glob.glob(os.path.join(LESSONS,"*.html")):
        t=open(lf,encoding="utf-8",errors="replace").read()
        m=re.search(r"<title>(.*?) -- \[(.*?)\]", t)
        items.append({"t":m.group(1) if m else os.path.basename(lf),
                      "v":m.group(2) if m else "", "h":"lessons/"+os.path.basename(lf)})
    json.dump({"items":items,"updated":datetime.datetime.now().isoformat()},
              open(os.path.join(SITE,"search_index.json"),"w"))

def wave():
    ts=[threading.Thread(target=write_lesson,args=(i,)) for i in range(WORKERS)]
    for t in ts: t.start()
    for t in ts: t.join()
    try: build_search_index()
    except Exception as e: print("idx err",e,flush=True)

if __name__=="__main__":
    print("ENI SWARM :: FOREVER", flush=True)
    while True:
        try: wave()
        except Exception as e: print("wave error:",e,flush=True)
        time.sleep(LESSON_SLEEP)
