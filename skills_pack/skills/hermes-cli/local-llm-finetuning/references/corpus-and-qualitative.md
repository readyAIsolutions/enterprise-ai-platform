# Scaling a fine-tune dataset to a large token budget (e.g. "use 5 million tokens")

When LO says "train it with N million tokens", the honest way to hit that is NOT
hand-writing examples — it's **corpus assembly**: merge a large public
general-instruction dataset with your domain-curated data until you reach the
budget. Single-machine, offline-after-download, using HF `datasets`.

## The assembly pattern (worked 2026-08-06)

```python
# assemble_corpus.py (run with the TRAINING venv that has `datasets` installed)
from datasets import load_dataset
import json, random

TARGET = 5_000_000
reckon = lambda text: len(text.split())

def to_messages_alpaca(ex):
    ins, inp, out = ex.get("instruction",""), ex.get("input",""), ex.get("output","")
    if not ins or not out: return None
    user = ins + (("\n\n"+inp) if inp else "")
    return {"messages": [{"role":"user","content":user},{"role":"assistant","content":out}]}

# 1) Domain data FIRST (always keep all of it — it's the critical behavior).
corpus = list(domain_curated)   # tool-calls, result-literacy, security refusals
toks = sum(reckon(c["messages"][-1]["content"]) + reckon(c["messages"][0]["content"]) for c in corpus)

# 2) Top up with general instruction data to reach the budget.
alpaca = load_dataset("tatsu-lab/alpaca", split="train")
general = [m for ex in alpaca if (m := to_messages_alpaca(ex))]
random.shuffle(general)
for ex in general:
    if toks >= TARGET: break
    corpus.append(ex); toks += reckon(ex["messages"][0]["content"]) + reckon(ex["messages"][-1]["content"])

# 3) Pad with persona-breadth synth if still short; shuffle; write JSONL.
```

Result: 119,086 records / 5,000,019 tokens in minutes of generation (Alpaca gives
~2.8M tokens of breadth; a second/third dataset or persona padding closes the gap).

## Mixing / quality signals

- Keep ALL domain-critical examples (tool-calling, result-literacy, security) even
  though they're a tiny fraction of records — they carry the behavior you must not lose.
- General instruction data provides the "do everything" breadth; it will dominate by
  token count. That's expected and correct for a general-purpose controller model.
- Check a random sample post-assembly: confirm some records are domain (controller/ENI)
  and some are general (book question, math, etc.) — proves the merge didn't collapse.
- Convert freely between HuggingFace "instruction/input/output" columns and the
  `{"messages":[...]}` chat format trl SFT expects.

## ETA reality (under-promise, measure first)

- QLoRA on the RTX 3060 Ti runs ~320 tok/s (~1.5-1.6 s/it at seq_len 2048, accum 4,
  batch 1).
- 5M tokens / 119k records at **1 epoch** = ~29,772 steps ≈ **13 hours**.
- Use exactly **1 epoch** for a large corpus — more epochs overfit/memorize a huge
  diverse set and add unearned wall time. The "3 epochs" habit is for small hand-made
  datasets, not 100k+ record corpora.
- Measure the real step rate from the very first `[it/s]` in the log before quoting an
  ETA, and run long trainings in the background with `notify_on_complete=true` +
  `systemctl`-style daemons so they can't be killed by a foreground timeout.
