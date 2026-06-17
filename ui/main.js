// Frontend-Logik des Privacy-Agenten.
// Spricht mit dem lokalen Python-Backend (FastAPI auf 127.0.0.1:8765) und --
// fuer die Einrichtung -- mit der Tauri-Huelle ueber invoke().

const API = "http://127.0.0.1:8765";

const el = (id) => document.getElementById(id);
const tauri = window.__TAURI__; // im Browser-Dev undefined

// --- Externe Links im System-Browser oeffnen ---------------------------------
// Die Tauri-WebView oeffnet selbst KEINE externen Links/Fenster (window.open und
// target=_blank tun nichts). Darum laesst das Backend sie via webbrowser.open auf.
async function openExternal(url) {
  if (!url) return;
  try {
    await fetch(`${API}/open-url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
  } catch { /* still */ }
}
window.openExternal = openExternal;

// Jeden Klick auf einen http(s)-Link zentral abfangen und extern oeffnen.
document.addEventListener("click", (e) => {
  const a = e.target.closest ? e.target.closest('a[href^="http"]') : null;
  if (a) {
    e.preventDefault();
    openExternal(a.getAttribute("href"));
  }
});

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
  el("loading").classList.add("hidden");
  el("wizard").classList.add("hidden");
  el("chat").classList.remove("hidden");
  el("open-brain").classList.remove("hidden");
  refreshStatus();
  loadProjects();
  if (!statusTimer) statusTimer = setInterval(refreshStatus, 5000);
}
window.enterChat = enterChat;

// --- Projekte (getrennte Arbeits-Threads) ------------------------------
const PDOT = { active: "pdot-active", paused: "pdot-paused", done: "pdot-done" };

async function loadProjects(reloadActive = true) {
  let list;
  try {
    list = (await (await fetch(`${API}/projects`)).json()).projects || [];
  } catch {
    return;
  }
  const bar = el("project-bar");
  bar.innerHTML = "";
  let activeId = null;
  list.forEach((p) => {
    if (p.active) activeId = p.id;
    const chip = document.createElement("div");
    chip.className = "proj-chip" + (p.active ? " active" : "");
    chip.innerHTML = `<span class="pdot ${PDOT[p.status] || "pdot-active"}"></span><span></span>`;
    chip.querySelector("span:nth-child(2)").textContent = p.name;
    chip.onclick = (e) => {
      if (e.target.dataset.act) return; // Aktionsknopf, nicht wechseln
      switchProject(p.id);
    };
    if (p.active) {
      const paused = p.status === "paused";
      chip.insertAdjacentHTML(
        "beforeend",
        `<button class="pact" data-act="toggle" title="${paused ? "Fortsetzen" : "Pausieren"}">${paused ? "▶" : "⏸"}</button>
         <button class="pact" data-act="del" title="Löschen">✕</button>`
      );
      chip.querySelector('[data-act="toggle"]').onclick = async () => {
        await fetch(`${API}/projects/${p.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: paused ? "active" : "paused" }),
        });
        loadProjects(false);
      };
      chip.querySelector('[data-act="del"]').onclick = async () => {
        await fetch(`${API}/projects/${p.id}`, { method: "DELETE" });
        loadProjects();
      };
    }
    bar.appendChild(chip);
  });
  const add = document.createElement("button");
  add.className = "proj-new";
  add.textContent = "+ Projekt";
  add.onclick = newProject;
  bar.appendChild(add);

  if (reloadActive && activeId) loadProjectMessages(activeId);
}

async function switchProject(id) {
  await fetch(`${API}/projects/${id}/activate`, { method: "POST" });
  el("suggest-bar").classList.add("hidden");
  await loadProjects(true);
}

async function loadProjectMessages(id) {
  try {
    const d = await (await fetch(`${API}/projects/${id}/messages`)).json();
    el("messages").innerHTML = "";
    (d.messages || []).forEach((m) =>
      addMessage(m.content, m.role === "user" ? "user" : "assistant")
    );
  } catch {
    /* still */
  }
}

async function newProject() {
  const name = prompt("Name des neuen Projekts:");
  if (!name) return;
  await fetch(`${API}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  el("messages").innerHTML = "";
  loadProjects(false);
}

// --- Hintergrund-Aufträge (Stufe B) ------------------------------------
let jobTimer = null;
let lastActive = 0;

el("bg-btn").addEventListener("click", async () => {
  const text = el("input").value.trim();
  if (!text) return;
  el("input").value = "";
  let urgent = false;
  try {
    const r = await fetch(`${API}/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal: text }),
    });
    urgent = (await r.json()).urgent;
  } catch {
    addMessage("⚠️ Konnte Hintergrund-Auftrag nicht starten.", "assistant");
    return;
  }
  addMessage((urgent ? "⏳⚡ Im Hintergrund (Vorrang): " : "⏳ Im Hintergrund: ") + text, "user");
  startJobPolling();
});

function startJobPolling() {
  if (jobTimer) return;
  jobTimer = setInterval(async () => {
    let d;
    try {
      d = await (await fetch(`${API}/jobs`)).json();
    } catch {
      return;
    }
    const bs = el("bg-status");
    if (d.active > 0) {
      bs.textContent = `⏳ ${d.active} Hintergrund-Auftrag(e) laufen …`;
      bs.classList.remove("hidden");
    } else {
      bs.classList.add("hidden");
    }
    // Wenn ein Auftrag fertig wurde -> Verlauf des aktiven Projekts nachladen.
    if (d.active < lastActive) loadProjects(true);
    lastActive = d.active;
    if (d.active === 0) {
      clearInterval(jobTimer);
      jobTimer = null;
    }
  }, 3000);
}

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
  } else if (res.type === "manual_cloud") {
    addMessage(res.text, "assistant");
    if (res.clipboard) {
      navigator.clipboard.writeText(res.clipboard).catch(() => {});
    }
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

// --- "Denkt nach …"-Indikator ------------------------------------------
function showThinking() {
  hideThinking();
  const div = document.createElement("div");
  div.id = "thinking";
  div.className = "msg msg-assistant thinking";
  div.innerHTML = `<span class="think-label">denkt nach</span>
    <span class="dots"><span></span><span></span><span></span></span>`;
  el("messages").appendChild(div);
  el("messages").scrollTop = el("messages").scrollHeight;
}
function hideThinking() {
  const t = el("thinking");
  if (t) t.remove();
}
function setComposerBusy(busy) {
  el("input").disabled = busy;
  const btn = el("composer").querySelector("button");
  if (btn) btn.disabled = busy;
}

el("composer").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = el("input").value.trim();
  if (!text) return;
  el("input").value = "";
  addMessage(text, "user");
  setComposerBusy(true);
  showThinking();
  try {
    const r = await fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    hideThinking();
    handleResult(await r.json());
  } catch {
    hideThinking();
    addMessage("⚠️ Backend nicht erreichbar.", "assistant");
  } finally {
    setComposerBusy(false);
    el("input").focus();
  }
});

// --- Einwilligungs-Dialog ----------------------------------------------
function showConsent(res) {
  el("consent-reason").textContent = res.reason;
  el("consent-data").textContent = res.data_preview || "(keine)";
  el("consent").classList.remove("hidden");

  const decide = async (approved) => {
    el("consent").classList.add("hidden");
    showThinking();
    try {
      const r = await fetch(`${API}/consent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pending_id: res.pending_id, approved }),
      });
      hideThinking();
      handleResult(await r.json());
    } catch {
      hideThinking();
      addMessage("⚠️ Backend nicht erreichbar.", "assistant");
    }
  };

  el("consent-yes").onclick = () => decide(true);
  el("consent-no").onclick = () => decide(false);
}

// --- Gedächtnis & Optimierung ------------------------------------------
function openBrain() {
  el("brain").classList.remove("hidden");
  el("brain-backdrop").classList.remove("hidden");
  loadModels();
  loadModelCatalog();
  loadEmergency();
  loadTailscale();
  loadLocalMatrix();
  loadMatrix();
  loadCatalog();
  loadMCP();
  loadProposals();
  loadMemory();
}

// --- Lokaler Matrix-Server (Docker, optional) --------------------------
async function loadLocalMatrix() {
  let s;
  try {
    s = await (await fetch(`${API}/local-matrix`)).json();
  } catch {
    return;
  }
  if (!s.docker) {
    el("lm-status").textContent =
      "Braucht Docker Desktop (nicht gefunden). Für die meisten reicht ein NAS-/externer Server.";
    el("lm-controls").classList.add("hidden");
    return;
  }
  el("lm-controls").classList.remove("hidden");
  if (s.server_name) el("lm-name").value = s.server_name;
  if (s.running) {
    el("lm-status").textContent = `🟢 Läuft · ${s.url} · Server-Name: ${s.server_name}`;
    el("lm-info").innerHTML =
      `Konten in Element anlegen mit Server-Adresse <b>${s.url}</b> und ` +
      `Registrierungs-Token <code>${s.token}</code>.`;
  } else {
    el("lm-status").textContent = "🔴 Gestoppt.";
    el("lm-info").textContent = "";
  }
}

el("lm-start").addEventListener("click", async () => {
  el("lm-info").textContent = "Starte … (beim ersten Mal lädt Docker das Image)";
  try {
    await fetch(`${API}/local-matrix/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ server_name: el("lm-name").value.trim() || "localhost" }),
    });
  } catch {
    el("lm-info").textContent = "Start nicht möglich.";
    return;
  }
  setTimeout(loadLocalMatrix, 2000);
});

el("lm-stop").addEventListener("click", async () => {
  await fetch(`${API}/local-matrix/stop`, { method: "POST" });
  loadLocalMatrix();
});

// --- Tailscale (privates Netz) -----------------------------------------
async function loadTailscale() {
  let s;
  try {
    s = await (await fetch(`${API}/tailscale`)).json();
  } catch {
    el("ts-status").textContent = "Backend nicht erreichbar.";
    return;
  }
  if (!s.installed) {
    el("ts-status").textContent = "🔴 Nicht installiert.";
    el("ts-install").classList.remove("hidden");
    el("ts-login").classList.add("hidden");
  } else if (s.logged_in) {
    el("ts-status").textContent = `🟢 Verbunden${s.name ? " · " + s.name : ""}${s.ip ? " (" + s.ip + ")" : ""}`;
    el("ts-install").classList.add("hidden");
    el("ts-login").classList.add("hidden");
  } else {
    el("ts-status").textContent = "🟡 Installiert, aber nicht angemeldet.";
    el("ts-install").classList.add("hidden");
    el("ts-login").classList.remove("hidden");
  }
}

el("ts-install").addEventListener("click", async () => {
  el("ts-msg").textContent = "Lade & installiere … (Windows-Abfrage bestätigen)";
  try {
    const d = await (await fetch(`${API}/tailscale/install`, { method: "POST" })).json();
    el("ts-msg").textContent = d.ok ? "Installiert." : "Fehlgeschlagen (Details im Log).";
  } catch {
    el("ts-msg").textContent = "Installation nicht möglich.";
  }
  loadTailscale();
});

el("ts-login").addEventListener("click", async () => {
  el("ts-msg").textContent = "Anmeldung startet – ggf. im Browser bestätigen …";
  try {
    const d = await (await fetch(`${API}/tailscale/login`, { method: "POST" })).json();
    el("ts-msg").textContent = d.message || "";
  } catch {
    el("ts-msg").textContent = "Anmeldung nicht möglich.";
  }
  setTimeout(loadTailscale, 4000);
});

// --- Messenger (Matrix) nachträglich konfigurieren ---------------------
async function loadMatrix() {
  try {
    const st = await (await fetch(`${API}/setup/state`)).json();
    const s = st.settings || {};
    el("mx2-server").value = s.matrix_homeserver || "";
    el("mx2-user").value = s.matrix_user || "";
    el("mx2-allow").value = s.matrix_allowed_users || "";
    el("mx2-admins").value = s.matrix_admin_users || "";
    el("mx2-pass").placeholder = s.matrix_password_set
      ? "Passwort gesetzt – leer lassen, um es zu behalten"
      : "Passwort des Agenten-Kontos";
    const c = st.connector || {};
    el("mx2-status").textContent = c.connected
      ? `🟢 verbunden${c.info ? " – " + c.info : ""}`
      : c.info
      ? `🔴 ${c.info}`
      : s.connector === "matrix"
      ? "🔴 nicht verbunden"
      : "Aus.";
  } catch {
    el("mx2-status").textContent = "Backend nicht erreichbar.";
  }
}

el("mx2-test").addEventListener("click", async () => {
  el("mx2-msg").textContent = "Teste …";
  try {
    const r = await fetch(`${API}/setup/matrix-test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        matrix_homeserver: el("mx2-server").value.trim(),
        matrix_user: el("mx2-user").value.trim(),
        matrix_password: el("mx2-pass").value,
      }),
    });
    const d = await r.json();
    el("mx2-msg").textContent = (d.ok ? "✅ " : "❌ ") + d.message;
  } catch {
    el("mx2-msg").textContent = "❌ Test nicht möglich.";
  }
});

el("mx2-save").addEventListener("click", async () => {
  const settings = {
    connector: "matrix",
    matrix_homeserver: el("mx2-server").value.trim(),
    matrix_user: el("mx2-user").value.trim(),
    matrix_allowed_users: el("mx2-allow").value.trim(),
    matrix_admin_users: el("mx2-admins").value.trim(),
  };
  const pass = el("mx2-pass").value;
  if (pass) settings.matrix_password = pass; // nur überschreiben, wenn eingegeben
  el("mx2-msg").textContent = "Speichere & verbinde …";
  try {
    await fetch(`${API}/setup/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings }),
    });
    el("mx2-pass").value = "";
    setTimeout(loadMatrix, 1500); // Status nach (Neu-)Verbindung aktualisieren
    el("mx2-msg").textContent = "Gespeichert – verbinde …";
  } catch {
    el("mx2-msg").textContent = "Speichern fehlgeschlagen.";
  }
});

el("mx2-off").addEventListener("click", async () => {
  await fetch(`${API}/setup/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ settings: { connector: "none" } }),
  });
  el("mx2-msg").textContent = "Deaktiviert.";
  loadMatrix();
});

// --- MCP-Vorlagen (Ein-Klick) ------------------------------------------
async function loadCatalog(force = false) {
  const box = el("mcp-templates");
  try {
    const r = await fetch(`${API}/mcp/catalog${force ? "?refresh=true" : ""}`);
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

el("mcp-cat-refresh").addEventListener("click", () => loadCatalog(true));

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
  if (t.login === "ms365") {
    html += `<div class="ms365-login">
      <button type="button" class="btn-secondary tpl-mslogin">🔑 Mit Microsoft anmelden</button>
      <div class="ms365-result muted"></div>
    </div>`;
  }
  html += `<label class="toggle"><input type="checkbox" class="tpl-trust" />
      <span>Vertrauen – ohne Rückfrage ausführen</span></label>
    <div class="inline-row">
      <button type="button" class="btn-secondary tpl-install">Installieren</button>
      <span class="muted tpl-msg"></span>
    </div>`;
  f.innerHTML = html;
  host.appendChild(f);

  if (t.runtime) ensureRuntimeUI(t.runtime, f.querySelector(".tpl-runtime"));

  const msBtn = f.querySelector(".tpl-mslogin");
  if (msBtn) {
    const out = f.querySelector(".ms365-result");
    msBtn.onclick = async () => {
      msBtn.disabled = true;
      out.innerHTML = "Anmeldung wird gestartet … (Browser öffnet sich gleich)";
      try {
        const r = await fetch(`${API}/ms365/login`, { method: "POST" });
        const d = await r.json();
        if (d.code) {
          out.innerHTML = `Gib im Browser diesen Code ein:
            <div class="ms365-code">${d.code}</div>
            <a href="${d.url}" target="_blank" rel="noopener">Seite öffnen</a>
            <p class="muted">Nach erfolgreicher Anmeldung unten auf „Installieren" klicken.</p>`;
        } else {
          out.innerHTML = `<a href="${d.url}" target="_blank" rel="noopener">Anmeldeseite öffnen</a>
            <pre class="ms365-raw">${(d.raw || d.message || "Keine Code-Ausgabe erkannt.").replace(/</g, "&lt;")}</pre>`;
        }
      } catch {
        out.textContent = "Backend nicht erreichbar.";
      }
      msBtn.disabled = false;
    };
  }

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
    const anyFailed = servers.some((s) => !((d.status || {})[s.name] || {}).connected);
    const head = document.createElement("div");
    head.className = "inline-row";
    head.innerHTML = `<button id="mcp-reload" class="btn-ghost" title="Skills neu starten">↻ neu verbinden</button>
      <span id="mcp-reload-msg" class="muted"></span>`;
    if (anyFailed) {
      head.querySelector("#mcp-reload-msg").textContent =
        "Tipp: Skills laden beim ersten Mal aus dem Netz – erneut verbinden hilft oft.";
    }
    box.appendChild(head);
    head.querySelector("#mcp-reload").onclick = async () => {
      el("mcp-reload-msg").textContent = "Starte Skills neu … (kann beim ersten Mal dauern)";
      try { await fetch(`${API}/mcp/reload`, { method: "POST" }); } catch {}
      loadMCP();
    };
    servers.forEach((s) => {
      const st = (d.status || {})[s.name] || {};
      const ok = st.connected;
      const count = st.tools != null ? `${st.tools} Werkzeug(e)` : "";
      const row = document.createElement("div");
      row.className = "mem-item";
      const info = ok ? count : (st.error || "nicht verbunden");
      row.innerHTML = `<span>${ok ? "🟢" : "🔴"} <b></b>
          <span class="muted mcp-info"></span></span>
        <button class="mem-del" title="Entfernen">🗑</button>`;
      row.querySelector("b").textContent = s.name;
      const infoEl = row.querySelector(".mcp-info");
      infoEl.textContent = info;
      infoEl.title = info; // volle Fehlermeldung beim Drüberfahren
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
    el("autodl-toggle").checked = !!d.auto_download_models;
    const dl = d.downloading || [];
    el("dl-status").textContent = dl.length
      ? `⬇ Lädt im Hintergrund: ${dl.join(", ")} …`
      : "";
  } catch {
    el("pull-msg").textContent = "Backend nicht erreichbar.";
  }
}

async function loadModelCatalog(force = false) {
  let d;
  try {
    d = await (await fetch(`${API}/models/catalog${force ? "?refresh=true" : ""}`)).json();
  } catch {
    return;
  }
  const box = el("model-catalog");
  box.innerHTML = "";
  (d.models || []).forEach((m) => {
    const busy = m.installed || m.downloading;
    const state = m.installed ? "✅ installiert" : m.downloading ? "⬇ lädt …" : "";
    const row = document.createElement("label");
    row.className = "cat-row";
    row.innerHTML = `<input type="checkbox" data-name="${m.name}" ${busy ? "checked disabled" : ""} />
      <span class="cat-main"><b></b> <span class="muted">${m.size}</span>
        <br><span class="cat-desc muted"></span></span>
      <span class="cat-state">${state}</span>`;
    row.querySelector("b").textContent = m.label;
    row.querySelector(".cat-desc").textContent = m.description;
    box.appendChild(row);
  });
}

el("catalog-refresh").addEventListener("click", () => loadModelCatalog(true));

el("model-dl").addEventListener("click", async () => {
  const picks = [...el("model-catalog").querySelectorAll("input[data-name]:checked:not([disabled])")];
  if (!picks.length) return;
  for (const cb of picks) {
    await fetch(`${API}/model/pull`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: cb.dataset.name }),
    });
  }
  loadModelCatalog();
  loadModels();
});

el("autodl-toggle").addEventListener("change", async (e) => {
  await fetch(`${API}/setup/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ settings: { auto_download_models: e.target.checked } }),
  });
});

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

// --- Modell-Sperre + Notfall-Hilfe -------------------------------------
async function saveSettings(obj) {
  await fetch(`${API}/setup/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ settings: obj }),
  });
}

function refreshEmergencyRows(orKeySet) {
  const mode = el("cloud-mode").value;
  el("browser-provider-row").classList.toggle("hidden", mode !== "browser");
  el("api-options").classList.toggle("hidden", mode !== "api");
  el("openrouter-row").classList.toggle("hidden", el("cloud-provider").value !== "openrouter");
  if (orKeySet !== undefined) {
    el("openrouter-status").textContent = orKeySet
      ? "🟢 Mit OpenRouter verbunden."
      : "Noch nicht angemeldet.";
  }
}

async function loadEmergency() {
  try {
    const st = await (await fetch(`${API}/setup/state`)).json();
    const s = st.settings || {};
    el("lock-toggle").checked = !!s.model_locked;
    el("cloud-mode").value = s.cloud_mode || "api";
    el("browser-provider").value = s.browser_provider || "claude";
    el("cloud-provider").value = s.cloud_provider || "openrouter";
    el("openrouter-model").value = s.openrouter_model || "";
    el("autopilot-toggle").disabled = !!s.model_locked; // bei Sperre sichtbar aus
    el("local-backend").value = s.local_backend || "ollama";
    el("local-openai-url").value = s.local_openai_base_url || "";
    el("local-openai-model").value = s.local_openai_model || "";
    toggleBackendUI();
    loadServerPresets();
    refreshEmergencyRows(!!s.openrouter_api_key_set);
  } catch {
    /* still */
  }
}

el("lock-toggle").addEventListener("change", async (e) => {
  await saveSettings({ model_locked: e.target.checked });
  el("autopilot-toggle").disabled = e.target.checked;
});

// --- Lokaler Motor: Ollama oder OpenAI-kompatibler Server ---------------
let _serverPresets = {};

function toggleBackendUI() {
  const openai = el("local-backend").value === "openai";
  el("openai-backend-row").classList.toggle("hidden", !openai);
  el("ollama-only").classList.toggle("hidden", openai);
}

async function loadServerPresets() {
  if (Object.keys(_serverPresets).length) return; // nur einmal
  try {
    const d = await (await fetch(`${API}/local/servers`)).json();
    const sel = el("server-preset");
    (d.servers || []).forEach((s) => {
      _serverPresets[s.id] = s;
      const o = document.createElement("option");
      o.value = s.id;
      o.textContent = s.label;
      sel.appendChild(o);
    });
  } catch { /* still */ }
}

el("server-preset").addEventListener("change", () => {
  const p = _serverPresets[el("server-preset").value];
  if (p) el("local-openai-url").value = p.url;
});

el("server-launch").addEventListener("click", async () => {
  const kind = el("server-preset").value;
  const msg = el("server-launch-msg");
  if (!kind) { msg.textContent = "Bitte zuerst oben eine App/Server wählen."; return; }
  // Auswahl als Backend speichern, damit der Test danach passt.
  if (_serverPresets[kind]) el("local-openai-url").value = _serverPresets[kind].url;
  await saveSettings({
    local_backend: "openai",
    local_openai_base_url: el("local-openai-url").value.trim(),
  });
  el("local-backend").value = "openai";
  toggleBackendUI();
  msg.textContent = "Starte …";
  let d;
  try {
    d = await (await fetch(`${API}/local/launch`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind }),
    })).json();
  } catch { msg.textContent = "🔴 Konnte nicht starten (Backend nicht erreichbar)."; return; }
  // Hinweis: window.open() funktioniert in der Tauri-WebView nicht -> das Backend
  // oeffnet die Download-Seite selbst (webbrowser). Wir zeigen die Adresse zusaetzlich.
  msg.textContent = d.message || "";
  if (d.busy) {
    const poll = setInterval(async () => {
      try {
        const st = await (await fetch(`${API}/local/launch/status`)).json();
        msg.textContent = st.message || "";
        if (!st.busy) { clearInterval(poll); setTimeout(probeLocalBackend, 1500); }
      } catch { /* weiter */ }
    }, 2000);
  } else if (d.launched || d.running) {
    setTimeout(probeLocalBackend, 2500);
  }
});

async function probeLocalBackend() {
  try {
    const d = await (await fetch(`${API}/local/probe`)).json();
    el("local-backend-msg").textContent = d.available
      ? `🟢 Erreichbar${d.models && d.models.length ? " (" + d.models.length + " Modell(e))" : ""}.`
      : "🔴 Noch nicht erreichbar – Server startet evtl. noch oder API-Modus in der App aktivieren.";
  } catch { /* still */ }
}

el("local-backend").addEventListener("change", async () => {
  toggleBackendUI();
  await saveSettings({ local_backend: el("local-backend").value });
  refreshStatus();
});

el("local-backend-test").addEventListener("click", async () => {
  const msg = el("local-backend-msg");
  msg.textContent = "Speichere & teste …";
  await saveSettings({
    local_backend: "openai",
    local_openai_base_url: el("local-openai-url").value.trim() || "http://127.0.0.1:8080/v1",
    local_openai_model: el("local-openai-model").value.trim(),
  });
  try {
    const d = await (await fetch(`${API}/local/probe`)).json();
    msg.textContent = d.available
      ? `🟢 Erreichbar${d.models && d.models.length ? " (" + d.models.length + " Modell(e))" : ""}.`
      : "🔴 Nicht erreichbar – läuft der Server unter der angegebenen Adresse?";
  } catch {
    msg.textContent = "🔴 Test fehlgeschlagen (Backend nicht erreichbar).";
  }
  refreshStatus();
});

el("cloud-mode").addEventListener("change", () => refreshEmergencyRows());
el("cloud-provider").addEventListener("change", () => refreshEmergencyRows());

el("openrouter-login").addEventListener("click", async () => {
  el("openrouter-msg").textContent = "Browser öffnet sich – bitte anmelden …";
  try {
    await fetch(`${API}/oauth/openrouter/start`, { method: "POST" });
  } catch {
    el("openrouter-msg").textContent = "Konnte Anmeldung nicht starten.";
    return;
  }
  // Auf den Schlüssel warten (Callback speichert ihn).
  let tries = 0;
  const poll = setInterval(async () => {
    tries++;
    try {
      const st = await (await fetch(`${API}/setup/state`)).json();
      if (st.settings && st.settings.openrouter_api_key_set) {
        clearInterval(poll);
        el("openrouter-msg").textContent = "✅ Angemeldet.";
        el("openrouter-status").textContent = "🟢 Mit OpenRouter verbunden.";
      }
    } catch { /* weiter versuchen */ }
    if (tries > 60) clearInterval(poll); // nach ~2 Min aufgeben
  }, 2000);
});

el("cloud-mode-save").addEventListener("click", async () => {
  el("cloud-mode-msg").textContent = "Speichere …";
  await saveSettings({
    cloud_mode: el("cloud-mode").value,
    browser_provider: el("browser-provider").value,
    cloud_provider: el("cloud-provider").value,
    openrouter_model: el("openrouter-model").value.trim() || "openrouter/auto",
  });
  el("cloud-mode-msg").textContent = "Gespeichert.";
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
      el("loading").classList.add("hidden");
      el("open-brain").classList.add("hidden");
      el("chat").classList.add("hidden");
      el("wizard").classList.remove("hidden");
      window.Wizard.init(st); // wizard.js
    }
  } catch {
    // Backend noch nicht erreichbar -> sichtbare Meldung statt schwarz, dann erneut.
    setStatus("warn", "Verbinde mit Agent …");
    const msg = el("loading-msg");
    if (msg) msg.textContent = "Backend startet noch … (beim ersten Start kann das etwas dauern)";
    setTimeout(bootstrap, 1500);
  }
}
bootstrap();
