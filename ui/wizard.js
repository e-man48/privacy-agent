// Geführter Einrichtungs-Assistent -- für Menschen ohne Vorkenntnisse.
// Nutzt die globalen Helfer aus main.js (el, API, tauri, enterChat).

const Wizard = (() => {
  const STEPS = ["welcome", "install", "style", "autopilot", "cloud", "messenger", "done"];
  const OPTIONAL = new Set(["cloud", "messenger"]); // dürfen übersprungen werden
  let idx = 0;
  let modelReady = false;
  let installPoll = null;
  let installListenerBound = false;

  const cfg = {
    decision_style: "balanced",
    auto_local_upgrade: true,
    anthropic_api_key: "",
    connector: "none",
  };

  function init(state) {
    modelReady = !!state.model_ready;
    renderDots();
    show(0);
    wireNav();
    wireStepHandlers();
  }

  // --- Navigation -------------------------------------------------------
  function renderDots() {
    const box = el("wizard-progress");
    box.innerHTML = "";
    STEPS.forEach((_, i) => {
      const d = document.createElement("span");
      d.className = "wdot";
      d.dataset.i = i;
      box.appendChild(d);
    });
  }

  function show(i) {
    idx = i;
    const name = STEPS[i];
    document.querySelectorAll(".wstep").forEach((s) => {
      s.classList.toggle("hidden", s.dataset.step !== name);
    });
    document.querySelectorAll(".wdot").forEach((d, di) => {
      d.classList.toggle("active", di === i);
      d.classList.toggle("done", di < i);
    });
    el("wiz-back").style.visibility = i === 0 ? "hidden" : "visible";
    el("wiz-skip").style.visibility = OPTIONAL.has(name) ? "visible" : "hidden";
    const next = el("wiz-next");
    next.textContent = name === "welcome" ? "Los geht's" : name === "done" ? "Loslegen 🚀" : "Weiter";
    updateNextEnabled();
    if (name === "install") {
      if (modelReady) {
        el("setup-bar").style.width = "100%";
        el("install-done").classList.remove("hidden");
        el("install-start").classList.add("hidden");
        el("setup-msg").textContent = "";
      }
      startInstallPolling();
    } else {
      stopInstallPolling();
    }
    if (name === "done") buildSummary();
  }

  function updateNextEnabled() {
    // Auf dem Installations-Schritt erst weiter, wenn die KI bereit ist.
    const blocked = STEPS[idx] === "install" && !modelReady;
    el("wiz-next").disabled = blocked;
    el("wiz-next").classList.toggle("btn-disabled", blocked);
  }

  function wireNav() {
    el("wiz-next").addEventListener("click", onNext);
    el("wiz-back").addEventListener("click", () => show(Math.max(0, idx - 1)));
    el("wiz-skip").addEventListener("click", () => { commitStep(); show(idx + 1); });
  }

  async function onNext() {
    commitStep();
    if (STEPS[idx] === "done") return finish();
    show(idx + 1);
  }

  // Sammelt die Eingaben des aktuellen Schritts in cfg.
  function commitStep() {
    const name = STEPS[idx];
    if (name === "autopilot") cfg.auto_local_upgrade = el("wiz-autopilot").checked;
    if (name === "cloud") cfg.anthropic_api_key = el("wiz-key").value.trim();
    if (name === "messenger") {
      if (el("wiz-matrix-on").checked) {
        cfg.connector = "matrix";
        cfg.matrix_homeserver = el("wiz-mx-server").value.trim();
        cfg.matrix_user = el("wiz-mx-user").value.trim();
        cfg.matrix_password = el("wiz-mx-pass").value;
        cfg.matrix_allowed_users = el("wiz-mx-allow").value.trim();
        cfg.matrix_admin_users = el("wiz-mx-admins").value.trim();
      } else {
        cfg.connector = "none";
      }
    }
  }

  // --- Schritt-spezifische Handler --------------------------------------
  function wireStepHandlers() {
    // Entscheidungsstil-Karten
    document.querySelectorAll(".choice").forEach((c) => {
      c.addEventListener("click", () => {
        document.querySelectorAll(".choice").forEach((x) => x.classList.remove("selected"));
        c.classList.add("selected");
        cfg.decision_style = c.dataset.style;
      });
    });

    // Installation starten
    el("install-start").addEventListener("click", runInstall);

    // Cloud-Schlüssel testen
    el("wiz-key-test").addEventListener("click", testKey);

    // Matrix-Felder ein-/ausblenden
    el("wiz-matrix-on").addEventListener("change", (e) => {
      el("wiz-matrix-fields").classList.toggle("hidden", !e.target.checked);
    });

    // Matrix-Verbindung testen
    el("wiz-mx-test").addEventListener("click", testMatrix);
  }

  async function testMatrix() {
    el("wiz-mx-msg").textContent = "Teste Verbindung …";
    try {
      const r = await fetch(`${API}/setup/matrix-test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          matrix_homeserver: el("wiz-mx-server").value.trim(),
          matrix_user: el("wiz-mx-user").value.trim(),
          matrix_password: el("wiz-mx-pass").value,
        }),
      });
      const d = await r.json();
      el("wiz-mx-msg").textContent = (d.ok ? "✅ " : "❌ ") + d.message;
    } catch {
      el("wiz-mx-msg").textContent = "❌ Test nicht möglich.";
    }
  }

  function installFailed(msg) {
    const btn = el("install-start");
    el("setup-bar").style.width = "0%";
    el("setup-msg").textContent = "⚠️ " + (msg || "Installation fehlgeschlagen.");
    btn.disabled = false;
    btn.textContent = "Erneut versuchen";
  }

  async function runInstall() {
    const btn = el("install-start");
    btn.disabled = true;
    btn.blur(); // entfernt die blaue Fokus-Markierung
    btn.textContent = "Installiere …";
    el("setup-msg").textContent = "Installation läuft … (kann einige Minuten dauern)";

    if (!tauri) {
      el("setup-msg").textContent =
        "Hinweis: Im Browser bitte einmalig 'python -m setup.first_run' ausführen. " +
        "Dieser Schritt entfällt in der fertigen App.";
      btn.disabled = false;
      btn.textContent = "Jetzt installieren";
      return;
    }

    // Fortschritts-Listener nur einmal binden.
    if (!installListenerBound) {
      installListenerBound = true;
      await tauri.event.listen("setup-progress", (e) => {
        const p = e.payload || {};
        if (p.progress != null) el("setup-bar").style.width = `${Math.round(p.progress * 100)}%`;
        if (p.message) el("setup-msg").textContent = p.message;
        if (p.stage === "error") installFailed(p.message);
      });
    }

    try {
      await tauri.core.invoke("run_setup");
      // Erfolg erkennt das Polling (model_ready) und blendet den Knopf aus.
    } catch (err) {
      installFailed(String(err));
    }
  }

  function startInstallPolling() {
    if (installPoll) return;
    installPoll = setInterval(async () => {
      try {
        const r = await fetch(`${API}/setup/state`);
        const st = await r.json();
        if (st.model_ready && !modelReady) {
          modelReady = true;
          el("setup-bar").style.width = "100%";
          el("install-done").classList.remove("hidden");
          el("install-start").classList.add("hidden");
          el("setup-msg").textContent = "";
          updateNextEnabled();
        }
      } catch { /* Backend evtl. kurz weg */ }
    }, 2000);
  }

  function stopInstallPolling() {
    if (installPoll) { clearInterval(installPoll); installPoll = null; }
  }

  async function testKey() {
    const key = el("wiz-key").value.trim();
    el("wiz-key-msg").textContent = "Teste …";
    try {
      const r = await fetch(`${API}/setup/cloud-test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: key }),
      });
      const d = await r.json();
      el("wiz-key-msg").textContent = (d.ok ? "✅ " : "❌ ") + d.message;
    } catch {
      el("wiz-key-msg").textContent = "❌ Test nicht möglich.";
    }
  }

  // --- Abschluss --------------------------------------------------------
  const STYLE_LABEL = { cautious: "Vorsichtig", balanced: "Ausgewogen", autonomous: "Selbstständig" };

  function buildSummary() {
    const lines = [
      `🧭 Verhalten: <b>${STYLE_LABEL[cfg.decision_style]}</b>`,
      `⬆️ Autopilot: <b>${cfg.auto_local_upgrade ? "an" : "aus"}</b>`,
      `☁️ Cloud-Hilfe: <b>${cfg.anthropic_api_key ? "eingerichtet" : "aus"}</b>`,
      `💬 Messenger: <b>${cfg.connector === "matrix" ? "Matrix" : "aus"}</b>`,
    ];
    el("wiz-summary").innerHTML = lines.map((l) => `<div>${l}</div>`).join("");
  }

  async function finish() {
    el("wiz-next").disabled = true;
    el("wiz-next").textContent = "Speichere …";
    try {
      await fetch(`${API}/setup/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ settings: { ...cfg, onboarded: true } }),
      });
    } catch { /* trotzdem fortfahren */ }
    stopInstallPolling();
    window.enterChat();
  }

  return { init };
})();

window.Wizard = Wizard;
