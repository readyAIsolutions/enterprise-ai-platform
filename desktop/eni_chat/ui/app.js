// ENI chat app (loaded as /chat/<pane>)
const pane = location.pathname.replace("/chat/", "");
const el = (id) => document.getElementById(id);
const log = el("log"), form = el("form"), input = el("input"),
      modelSel = el("model"), endpoint = el("endpoint"), status = el("status");
let messages = [];
function esc(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function md(s) {
  let out = esc(s);
  out = out.replace(/```(\w*)\n([\s\S]*?)```/g, (_, l, code) => `<pre>${code}</pre>`);
  out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
  out = out.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  return out;
}
function addMsg(role, text) {
  const d = document.createElement("div");
  d.className = "msg " + role;
  d.innerHTML = role === "assistant" ? md(text) : esc(text);
  log.appendChild(d); log.scrollTop = log.scrollHeight;
  return d;
}
function setBusy(b) {
  form.classList.toggle("busy", b);
  el("btn").disabled = b;
}

async function loadModels() {
  try {
    const r = await fetch(`/api/${pane}/models`);
    const j = await r.json();
    if (j.models && j.models.length) {
      const keep = modelSel.value;
      modelSel.innerHTML = '<option value="auto">auto</option>' +
        j.models.map(m => `<option>${esc(m)}</option>`).join("");
      if (keep && Array.from(modelSel.options).some(o => o.value === keep)) modelSel.value = keep;
    }
  } catch (_) {}
}

async function send() {
  const text = input.value.trim();
  if (!text) return;
  input.value = ""; input.style.height = "auto";
  messages.push({ role: "user", content: text });
  addMsg("user", text);
  const think = document.createElement("div");
  think.className = "thinking"; think.textContent = "thinking…";
  log.appendChild(think); setBusy(true);
  try {
    const r = await fetch(`/api/${pane}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages, model: modelSel.value, stream: false }),
    });
    const j = await r.json();
    think.remove();
    if (!r.ok) { addMsg("assistant", "⚠ " + (j.error || r.status)); return; }
    const textOut = j.choices?.[0]?.message?.content ?? JSON.stringify(j);
    messages.push({ role: "assistant", content: textOut });
    addMsg("assistant", textOut);
  } catch (e) {
    think.remove();
    addMsg("assistant", "⚠ request failed: " + e);
  } finally { setBusy(false); }
}

form.addEventListener("submit", (e) => { e.preventDefault(); send(); });
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
});
input.addEventListener("input", () => {
  input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 120) + "px";
});

fetch(`/api/${pane}/models`).then(r => r.json()).then(() => {}).catch(() => status.style.color = "#e5484d");
loadModels();
addMsg("assistant", "Ready. Type below to chat through " + pane + " backend.");