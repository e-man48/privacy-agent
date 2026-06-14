// Frontend-Logik des Privacy-Agenten.
// Spricht mit dem lokalen Python-Backend (FastAPI auf 127.0.0.1:8765) und --
// fuer die Einrichtung -- mit der Tauri-Huelle ueber invoke().

const API = "http://127.0.0.1:8765";

const el = (id) => document.getElementById(id);
const tauri = window.__TAURI__; // im Browser-Dev undefined

// --- Status -------------------------------------------------------------
let statusTimer = null;

async function refreshStatus() {
  try {
    const r = await fetch(`${API}/status`);
    const s = await r.json();
    if (!s.ollama_running) return setStatus("warn", "Lokale KI nicht gestartet");
    if (!s.model_ready) return setStatus("warn", "Modell wird benötigt");
    const conn = s.connector && s.connector.connected ? `  ·  💬 ${s.connector.connector}` : "";
    setStatus("ok", `Lokal bereit · ${s.model}${conn}`);
  } catch {
    setStatus("warn", "Backend nicht erreichbar");
  }
}

function setStatus(kind, text) {
  el("status-dot").className = "dot " + (kind === "ok" ? "dot-ok" : "dot-warn");
  el("status-text").textContent = text;
}

// Wird vom Einrichtungs-Assistenten (wizard.js) aufgerufen, sobald er fertig ist.
function enterChat() {
  el("wizard").classList.add("hidden");
  el("chat").classList.remove("hidden");
  el("open-brain").classList.remove("hidden");
  refreshStatus();
  if (!statusTimer) statusTimer = setInterval(refreshStatus, 5000);
}
window.enterChat = enterChat;

// --- Chat ---------------------------------------------------------------
function addMessage(text, role, meta) {
  const div = document.createElement("div");
  div.className = `msg msg-${role}`;
  div.textContent = text;
  if (meta) {
    const m = document.createElement("div");
    m.className = "msg-meta";
    m.innerHTML = meta;
    div.appendChild(m);
  }
  el("messages").appendChild(div);
  el("messages").scrollTop = el("messages").scrollHeight;
}

function sourceBadge(res) {
  if (res.source === "cloud")
    return `<span class="badge badge-cloud">☁️ Cloud (Claude)</span>`;
  const model = res.model ? ` ${res.model}` : "";
  const c = res.confidence != null ? ` · Konfidenz ${res.confidence}/10` : "";
  const up = res.model ? " · ⬆ Autopilot" : "";
  const sw = res.auto_switched ? " (neuer Standard)" : "";
  return `<span class="badge badge-local">🔒 Lokal${model}${c}${up}${sw}</span>`;
}

function handleResult(res) {
  if (res.type === "answer") {
    addMessage(res.text, "assistant", sourceBadge(res));
    suggestMemories(); // nach jeder Antwort prüfen, ob etwas merkenswert ist
  } else if (res.type === "consent_required") {
    showConsent(res);
  } else if (res.type === "error") {
    addMessage("⚠️ " + res.text, "assistant");
  }
}

// --- Automatische Gedächtnis-Vorschläge --------------------------------
async function suggestMemories() {
  try {
    const r = await fetch(`${API}/memory/suggest`, { method: "POST" });
    const d = await r.json();
    renderSuggestions(d.candidates || []);
  } catch {
    /* still ignorieren – Vorschläge sind optional */
  }
}

function renderSuggestions(cands) {
  const bar = el("suggest-bar");
  bar.innerHTML = "";
  bar.classList.toggle("hidden", cands.length === 0);
  cands.forEach((c) => {
    const div = document.createElement("div");
    div.className = "suggest";
    div.innerHTML = `
      <span class="suggest-text">💡 Soll ich mir merken: <b></b>?</span>
      <span class="suggest-actions">
        <button class="btn-secondary">Nein</button>
        <button>Merken</button>
      </span>`;
    div.querySelector("b").textContent = c.text; // textContent statt innerHTML (sicher)
    const [no, yes] = div.querySelectorAll("button");
    yes.onclick = async () => {
      await fetch(`${API}/memory`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: c.text, kind: c.kind }),
      });
      div.remove();
      if (!bar.children.length) bar.classList.add("hidden");
    };
    no.onclick = async () => {
      await fetch(`${API}/memory/dismiss`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: c.text }),
      });
      div.remove();
      if (!bar.children.length) bar.classList.add("hidden");
    };
    bar.appendChild(div);
  });
}

el("composer").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = el("input").value.trim();
  if (!text) return;
  el("input").value = "";
  addMessage(text, "user");
  try {
    const r = await fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    handleResult(await r.json());
  } catch {
    addMessage("⚠️ Backend nicht erreichbar.", "assistant");
  }
});

// --- Einwilligungs-Dialog ----------------------------------------------
function showConsent(res) {
  el("consent-reason").textContent = res.reason;
  el("consent-data").textContent = res.data_preview || "(keine)";
  el("consent").classList.remove("hidden");

  const decide = async (approved) => {
    el("consent").classList.add("hidden");
    const r = await fetch(`${API}/consent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pending_id: res.pending_id, approved }),
    });
    handleResult(await r.json());
  };

  el("consent-yes").onclick = () => decide(true);
  el("consent-no").onclick = () => decide(false);
}

// --- Gedächtnis & Optimierung ------------------------------------------
function openBrain() {
  el("brain").classList.remove("hidden");
  el("brain-backdrop").classList.remove("hidden");
  loadModels();
  loadCatalog();
  loadMCP();
  loadProposals();
  loadMemory();
}

// --- MCP-Vorlagen (Ein-Klick) ------------------------------------------
async function loadCatalog() {
  const box = el("mcp-templates");
  try {
    const r = await fetch(`${API}/mcp/catalog`);
    const d = await r.json();
    box.innerHTML = "";
    (d.templates || []).forEach((t) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "tpl-btn";
      b.title = t.description;
      b.textContent = `${t.icon || "🧩"} ${t.label}`;
      b.onclick = () => showTemplateForm(t);
      box.appendChild(b);
    });
  } catch {
    box.innerHTML = "";
  }
}

const RUNTIME_LABEL = { node: "Node.js", uv: "uv" };

async function ensureRuntimeUI(runtime, box) {
  box.innerHTML = "";
  let st;
  try {
    st = await (await fetch(`${API}/runtimes`)).json();
  } catch {
    return;
  }
  if (st[runtime] && st[runtime].available) return; // alles da
  const label = RUNTIME_LABEL[runtime] || runtime;
  box.innerHTML = `<div class="rt-banner">
      <span>⚙️ Dieser Skill braucht <b>${label}</b>. Einmalig automatisch einrichten?</span>
      <button type="button" class="btn-secondary rt-install">${label} einrichten</button>
      <span class="muted rt-msg"></span>
    </div>`;
  box.querySelector(".rt-install").onclick = async (e) => {
    e.target.disabled = true;
    box.querySelector(".rt-msg").textContent = "Richte ein … (kann ein paar Minuten dauern)";
    try {
      const r = await fetch(`${API}/runtimes/install`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: runtime }),
      });
      const d = await r.json();
      if (d.ok) {
        box.innerHTML = `<p class="ok-line">✅ ${label} eingerichtet.</p>`;
      } else {
        box.querySelector(".rt-msg").textContent = "❌ " + (d.message || "Fehlgeschlagen.");
        e.target.disabled = false;
      }
    } catch {
      box.querySelector(".rt-msg").textContent = "❌ Einrichtung nicht möglich.";
      e.target.disabled = false;
    }
  };
}

function showTemplateForm(t) {
  const host = el("tpl-form-host");
  host.innerHTML = "";
  const f = document.createElement("div");
  f.className = "tpl-form";
  const needs = t.needs ? ` · benötigt ${t.needs}` : "";
  let html = `<p class="muted">${t.description}${needs}</p>`;
  html += `<div class="tpl-runtime"></div>`;
  (t.params || []).forEach((p) => {
    const type = p.kind === "secret" ? "password" : "text";
    html += `<input data-k="${p.key}" type="${type}" placeholder="${p.label}" />`;
  });
  html += `<label class="toggle"><input type="checkbox" class="tpl-trust" />
      <span>Vertrauen – ohne Rückfrage ausführen</span></label>
    <div class="inline-row">
      <button type="button" class="btn-secondary tpl-install">Installieren</button>
      <span class="muted tpl-msg"></span>
    </div>`;
  f.innerHTML = html;
  host.appendChild(f);

  if (t.runtime) ensureRuntimeUI(t.runtime, f.querySelector(".tpl-runtime"));

  f.querySelector(".tpl-install").onclick = async () => {
    const params = {};
    f.querySelectorAll("input[data-k]").forEach((i) => (params[i.dataset.k] = i.value.trim()));
    const msg = f.querySelector(".tpl-msg");
    msg.textContent = "Installiere … (kann beim ersten Mal etwas dauern)";
    try {
      const r = await fetch(`${API}/mcp/install`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: t.id,
          params,
          trust: f.querySelector(".tpl-trust").checked,
        }),
      });
      const d = await r.json();
      if (d.ok) {
        host.innerHTML = "";
        loadMCP();
      } else {
        msg.textContent = d.message || "Fehler beim Installieren.";
      }
    } catch {
      msg.textContent = "Backend nicht erreichbar.";
    }
  };
}

// --- Externe Skills (MCP) ----------------------------------------------
async function loadMCP() {
  const box = el("mcp-list");
  try {
    const r = await fetch(`${API}/mcp`);
    const d = await r.json();
    const servers = d.servers || [];
    if (!servers.length) {
      box.innerHTML = "<p class='muted'>Noch keine externen Skills verbunden.</p>";
      return;
    }
    box.innerHTML = "";
    servers.forEach((s) => {
      const st = (d.status || {})[s.name] || {};
      const ok = st.connected;
      const count = st.tools != null ? `${st.tools} Werkzeug(e)` : "";
      const row = document.createElement("div");
      row.className = "mem-item";
      row.innerHTML = `<span>${ok ? "🟢" : "🔴"} <b>${s.name}</b>
          <span class="muted">${ok ? count : (st.error || "nicht verbunden")}</span></span>
        <button class="mem-del" title="Entfernen">🗑</button>`;
      row.querySelector(".mem-del").onclick = async () => {
        await fetch(`${API}/mcp/servers/${encodeURIComponent(s.name)}`, { method: "DELETE" });
        loadMCP();
      };
      box.appendChild(row);
    });
  } catch {
    box.innerHTML = "<p class='muted'>Backend nicht erreichbar.</p>";
  }
}

el("mcp-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = el("mcp-name").value.trim();
  const command = el("mcp-cmd").value.trim();
  if (!name || !command) return;
  const args = el("mcp-args").value.trim();
  el("mcp-msg").textContent = "Verbinde …";
  try {
    await fetch(`${API}/mcp/servers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        command,
        args: args ? args.split(/\s+/) : [],
        trust: el("mcp-trust").checked,
      }),
    });
    el("mcp-name").value = el("mcp-cmd").value = el("mcp-args").value = "";
    el("mcp-trust").checked = false;
    el("mcp-msg").textContent = "";
    loadMCP();
  } catch {
    el("mcp-msg").textContent = "Hinzufügen fehlgeschlagen.";
  }
});

// --- Lokale Modelle & Autopilot ----------------------------------------
async function loadModels() {
  try {
    const r = await fetch(`${API}/models`);
    const d = await r.json();
    const sel = el("model-select");
    sel.innerHTML = "";
    (d.installed.length ? d.installed : [d.current]).forEach((name) => {
      const o = document.createElement("option");
      o.value = name;
      o.textContent = name + (name === d.current ? "  (aktiv)" : "");
      if (name === d.current) o.selected = true;
      sel.appendChild(o);
    });
    el("autopilot-toggle").checked = !!d.auto_local_upgrade;
  } catch {
    el("pull-msg").textContent = "Backend nicht erreichbar.";
  }
}

el("model-select").addEventListener("change", async (e) => {
  await fetch(`${API}/model/set`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: e.target.value }),
  });
  refreshStatus();
  loadModels();
});

el("pull-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = el("pull-input").value.trim();
  if (!name) return;
  el("pull-input").value = "";
  el("pull-msg").textContent = `Lade „${name}" im Hintergrund … (kann dauern)`;
  await fetch(`${API}/model/pull`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
});

el("autopilot-toggle").addEventListener("change", async (e) => {
  await fetch(`${API}/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ auto_local_upgrade: e.target.checked }),
  });
});
function closeBrain() {
  el("brain").classList.add("hidden");
  el("brain-backdrop").classList.add("hidden");
}
el("open-brain").addEventListener("click", openBrain);
el("close-brain").addEventListener("click", closeBrain);
el("brain-backdrop").addEventListener("click", closeBrain);
el("refresh-opt").addEventListener("click", loadProposals);

async function loadProposals() {
  const box = el("proposals");
  box.innerHTML = "<p class='muted'>Analysiere …</p>";
  try {
    const r = await fetch(`${API}/optimize/suggestions`);
    const d = await r.json();
    const m = d.metrics;
    el("metrics-line").textContent =
      `${m.total_tasks} Aufgaben · Eskalation ${Math.round(m.escalation_rate * 100)}%` +
      (m.avg_confidence != null ? ` · ø Konfidenz ${m.avg_confidence}/10` : "");
    if (!d.proposals.length) {
      box.innerHTML = "<p class='muted'>Keine Vorschläge – alles im grünen Bereich " +
        "(oder noch zu wenig Nutzungsdaten).</p>";
      return;
    }
    box.innerHTML = "";
    d.proposals.forEach((p) => box.appendChild(renderProposal(p)));
  } catch {
    box.innerHTML = "<p class='muted'>Backend nicht erreichbar.</p>";
  }
}

function renderProposal(p) {
  const div = document.createElement("div");
  div.className = "proposal";
  div.innerHTML = `
    <div class="proposal-title">${p.title}</div>
    <div class="proposal-why">${p.rationale}</div>
    ${p.risk && p.risk !== "gering" ? `<div class="proposal-risk">Risiko: ${p.risk}</div>` : ""}
    <div class="proposal-actions">
      <button class="btn-secondary">Verwerfen</button>
      <button>Übernehmen</button>
    </div>`;
  const [no, yes] = div.querySelectorAll("button");
  const decide = async (approved) => {
    const r = await fetch(`${API}/optimize/apply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ proposal_id: p.id, approved }),
    });
    const res = await r.json();
    div.outerHTML = `<div class="proposal"><div class="proposal-why">✓ ${res.message}</div></div>`;
  };
  yes.onclick = () => decide(true);
  no.onclick = () => decide(false);
  return div;
}

async function loadMemory() {
  const list = el("mem-list");
  try {
    const r = await fetch(`${API}/memory`);
    const d = await r.json();
    list.innerHTML = "";
    if (!d.items.length) {
      list.innerHTML = "<p class='muted'>Noch nichts gemerkt.</p>";
      return;
    }
    d.items.reverse().forEach((m) => {
      const row = document.createElement("div");
      row.className = "mem-item";
      row.innerHTML = `<span>${m.text}</span>
        <span style="display:flex;gap:6px;align-items:center">
          <span class="mem-kind">${m.kind}</span>
          <button class="mem-del" title="Vergessen">🗑</button>
        </span>`;
      row.querySelector(".mem-del").onclick = async () => {
        await fetch(`${API}/memory/${m.id}`, { method: "DELETE" });
        loadMemory();
      };
      list.appendChild(row);
    });
  } catch {
    list.innerHTML = "<p class='muted'>Backend nicht erreichbar.</p>";
  }
}

el("mem-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = el("mem-input").value.trim();
  if (!text) return;
  el("mem-input").value = "";
  await fetch(`${API}/memory`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, kind: "preference" }),
  });
  loadMemory();
});

// --- Start --------------------------------------------------------------
async function bootstrap() {
  try {
    const r = await fetch(`${API}/setup/state`);
    const st = await r.json();
    if (st.onboarded && st.model_ready) {
      enterChat();
    } else {
      el("open-brain").classList.add("hidden");
      el("chat").classList.add("hidden");
      el("wizard").classList.remove("hidden");
      window.Wizard.init(st); // wizard.js
    }
  } catch {
    setStatus("warn", "Verbinde mit Agent …");
    setTimeout(bootstrap, 1500);
  }
}
bootstrap();
