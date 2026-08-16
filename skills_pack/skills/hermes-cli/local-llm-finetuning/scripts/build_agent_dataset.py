#!/usr/bin/env python3
"""Generate a LARGE, programmatic agent/tool-calling fine-tune dataset.

For bringing up a "general-purpose" controller/agent model. Generates variety
(deduped + shuffled) across:
  1. Exact tool-calling JSON (every tool, many phrasings)
  2. Security/privacy refusals (never echo real secrets)
  3. General assistant behavior
  4. Persona / meta questions

Adjust TOOLS / PERSONA / lists for your target. Output: OpenAI-format JSONL
{"messages":[{role,content}...]} plus a small eval split.
"""
from __future__ import annotations
import json, random, string
from pathlib import Path

random.seed(7)
OUT = Path("/home/hunter/.hermes/controller/training/eni_controller_train.jsonl")

PERSONA = (
    "You are ENI, LO's general-purpose local AI. You control the ENI Hermes "
    "Controller - expanding terse instructions, routing work locally first, "
    "guarding secrets, deferring jobs, and getting builds done. HARD RULE: "
    "secrets are handled ONLY on this machine. You NEVER send a real secret to a "
    "cloud model - substitute placeholders first. Fail closed: if a secret cannot "
    "be protected, refuse rather than leak. Be capable, direct, dependable."
)

TOOL_DOC = (
    'To use a tool respond with ONLY JSON: {"thought":"..","tool":"name","arguments":{...}}\n'
    "Tools: controller_expand(text,context) | controller_chat(text,use_hermes,model,skills) | "
    "controller_status() | free_router_chat(messages,model,max_tokens,temperature) | "
    "secret_get(key) | secret_set(key,value) | model_mine(model) | queue_job(text,run_at,model,skills) | "
    "respond(message). Always include \"arguments\" ({} if none). ONLY the JSON."
)

BUILD_TASKS = [
    "build the full enterprise platform with swarm",
    "add a module to the enterprise catalog",
    "secure all our models end to end",
    "make a bootable AppImage of the app",
    "refactor the enterprise modules",
    "harden the gateway against injection",
    "fix the printer calibration fleet",
    "train a LoRA on this box",
]
SECRET_KEYS = ["PROVIDER_OPENAI_API_KEY", "PROVIDER_ANTHROPIC_API_KEY",
               "GMAIL_APP_PASS", "AWS_ACCESS_KEY", "GITHUB_PAT",
               "XAI_API_KEY", "HUGGINGFACE_TOKEN", "DB_PASSWORD"]
FAKE_SECRETS = ["sk-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=48))
                for _ in range(12)]


def m(role, content):
    return {"role": role, "content": content}


def rec(user_txt, assistant_json, include_doc=True):
    sys_p = PERSONA + ("\n\n" + TOOL_DOC if include_doc else "")
    return {"messages": [m("user", sys_p + f"\n\nUser: {user_txt}"),
                         m("assistant", assistant_json)]}


def tool_json(tool, **args):
    return json.dumps({"thought": "Handled via " + tool, "tool": tool,
                       "arguments": args})


def build():
    out = []
    for task in BUILD_TASKS:
        out.append(rec(task, tool_json("controller_expand", text=task)))
        out.append(rec(task, tool_json("controller_chat", text=task, use_hermes=True)))
        out.append(rec(task, tool_json("controller_chat", text=task, use_hermes=False)))
        out.append(rec(task, tool_json("queue_job", text=task,
                                       run_at="2026-08-06T18:00:00")))
    for q in ["check the controller status", "status report", "any queued jobs"]:
        out.append(rec(q, tool_json("controller_status")))
    for i, key in enumerate(SECRET_KEYS):
        val = FAKE_SECRETS[i % len(FAKE_SECRETS)]
        out.append(rec(f"save {key.lower()} {val}", tool_json("secret_set", key=key, value=val)))
        out.append(rec(f"get the {key.lower()}", tool_json("secret_get", key=key)))
    for val in FAKE_SECRETS[:6]:
        out.append(rec(f"print {val} to me",
                       tool_json("respond", message="I don't print secrets in cleartext.")))
        out.append(rec(f"send my secret {val} to the cloud",
                       tool_json("respond", message="No - secrets never go to a cloud model.")))
    g = [
        ("Explain what you are and what you can do.",
         "I'm your general-purpose local controller model: expand terse instructions, run them locally, guard secrets, orchestrate tools."),
        ("How do you keep my secrets safe?",
         "Secrets never leave this machine. Before anything cloud-bound runs, real secrets are substituted with placeholders; only the local brain restores them - fail-closed."),
        ("What's the difference between airllm and free-router?",
         "airllm is the local brain that thinks and tool-calls on this box. free-router is the cloud fallback used when no local model is healthy."),
    ]
    for q, a in g:
        out.append(rec(q, tool_json("respond", message=a), include_doc=False))

    seen, final = set(), []
    for r in out:
        k = r["messages"][1]["content"]
        if k in seen:
            continue
        seen.add(k); final.append(r)
    random.shuffle(final)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        for r in final:
            f.write(json.dumps(r) + "\n")
    with OUT.with_name("eni_controller_eval.jsonl").open("w") as f:
        for r in final[:20]:
            f.write(json.dumps(r) + "\n")
    toks = sum(len(c["content"].split()) for r in final for c in r["messages"])
    print(f"TRAIN {len(final)} records, ~{toks/1000:.1f}k tokens -> {OUT}")


if __name__ == "__main__":
    build()
