# AGENTS.md — Projektkontext für KI-Agenten

> Diese Datei beschreibt das Projekt **Privacy-Agent** maschinenlesbar und präzise,
> damit ein KI-Agent (Coding-Assistent) den Code versteht, sicher erweitert und
> die **Datenschutz-Invarianten niemals verletzt**. Für Menschen: siehe
> [HANDBUCH.md](HANDBUCH.md).

---

## 1. Zweck in einem Satz

Ein **lokal-zuerst** arbeitender, **DSGVO-konformer** KI-Agent: Er beantwortet
Aufgaben mit einer **lokalen Open-Source-KI (Ollama)** und eskaliert **nur nach
ausdrücklicher Einwilligung** und nur im Notfall an eine Cloud-KI. Installierbar
auf Windows/macOS/Linux; die lokale KI ist Teil des Setups.

## 2. Unverhandelbare Invarianten (NIEMALS brechen)

Diese Regeln haben Vorrang vor jeder anderen Änderung. Wer Code anfasst, hält sie ein:

1. **Kein Datenabfluss ohne Einwilligung.** Jede Operation, die Daten das Gerät
   verlassen lässt — Cloud-LLM, Web-Suche, externe Skills, Messenger — läuft
   ausschließlich über den Einwilligungs-Pfad (`router._consent` →
   `PendingAction` → Endpoint `POST /consent`). Werkzeuge markieren das per
   `leaves_device=True` / `requires_consent=True` in `agent/tools/registry.py`.
2. **Lokal zuerst.** Die lokale KI wird immer zuerst versucht. Cloud ist Notfall,
   nie Default-Pfad. Reihenfolge der Eskalation: **lokal → OpenRouter → Claude**.
3. **Jeder Cloud-/Außen-Kontakt wird protokolliert** in `consent_log.jsonl`
   (`agent/consent_log.py`). Protokollierung nicht umgehen.
4. **Abo-Zugangsdaten sind keine API.** Ein Abo-Login (claude.ai etc.) darf nicht
   als API missbraucht werden (ToS). Dafür existiert der `browser`-Modus
   (Übergabe per Zwischenablage) bzw. OpenRouter/eigener API-Schlüssel.
5. **Selbstoptimierung ist eingezäunt.** Der Optimierer darf **nur** die Werte in
   `config._TUNABLE` ändern, nur über `config.set_override()`, nur nach Genehmigung.
   **Kein Schreibzugriff auf Quellcode.**
6. **Modell-Sperre respektieren.** Bei `MODEL_LOCKED=true` darf der Agent
   (Autopilot/Optimierer) das Modell nicht wechseln/herunterladen — nur der Mensch.
7. **Pro-Person-Trennung.** Gedächtnis und Rechte sind pro `principal` getrennt
   (`agent/principals.py`). Owner-Scoping beim Gedächtnis nicht aufheben.

## 3. Architektur

```
┌─────────────────────────────────────────────────────────────┐
│  Tauri v2 Shell (Rust, src-tauri/)  ── Fenster + Sidecar-Start │
│     └─ startet Python-Backend als Sidecar (PyInstaller-Exe)    │
├─────────────────────────────────────────────────────────────┤
│  Python-Backend (FastAPI, agent/)  ── 127.0.0.1:8765           │
│     router → local_llm (Ollama) → [Einwilligung] → cloud_llm   │
│     + memory/embeddings, mcp_client, autopilot, connectors …   │
├─────────────────────────────────────────────────────────────┤
│  Ollama (lokale LLM-Runtime)        ── 127.0.0.1:11434         │
│  MCP-Skills (Subprozesse, stdio)    ── npx/uvx je Skill        │
└─────────────────────────────────────────────────────────────┘
```

- **Frontend/GUI:** `ui/` (Vanilla JS, kein Framework) — `index.html`, `main.js`,
  `wizard.js`, `styles.css`. Spricht das Backend per `fetch` auf `http://127.0.0.1:8765`.
- **Backend-Start:** `launcher.py` / `agent/main.py` (uvicorn). Lifespan startet
  Connectors, Scheduler, MCP-Clients.
- **Build:** `build_sidecar.py` (PyInstaller), `.github/workflows/build.yml`
  (Multi-OS), NSIS-Hooks `src-tauri/installer-hooks.nsh` (killt laufenden Prozess
  vor Neuinstallation).

## 4. Modul-Landkarte (`agent/`)

| Modul | Verantwortung |
|---|---|
| `main.py` | FastAPI-App + alle HTTP-Endpunkte, Lifespan |
| `config.py` | Zentrale Einstellungen, Overrides, `_TUNABLE`, Datenpfade |
| `router.py` | Kernlogik: lokale Bearbeitung, Werkzeug-Schleife, Eskalation/Einwilligung |
| `local_llm.py` | Lokaler Motor (chat/list_models/has_model/is_available). Dispatch per `config.LOCAL_BACKEND`: `ollama` (`/api/chat`) **oder** `openai` (OpenAI-kompatibel `/v1/chat/completions`: llama.cpp/llamafile/LM Studio). Beide **streamen** (gegen „Read timed out"). `ensure_running()` findet/startet Ollama (Lifespan + vor Anfrage), damit „nicht erreichbar" gar nicht erst auftritt. |
| `cloud_llm.py` | Cloud-Kette: `_providers()` = OpenRouter→Anthropic, `chat()` mit Auto-Fallback |
| `openrouter_auth.py` | OpenRouter OAuth (PKCE) Login-Flow |
| `ms365_auth.py` | Microsoft-365-Geräte-Code-Login für den Outlook-Skill |
| `autopilot.py` | Autonomer Wechsel auf größeres lokales Modell (+ Auto-Download), wenn nicht gesperrt |
| `downloads.py` | Hintergrund-Download-Manager für Ollama-Modelle (geteilt) |
| `memory.py` | Langzeit-Gedächtnis (JSONL), Vorschläge, Owner-Scoping |
| `embeddings.py` | Semantische Embeddings (nomic-embed-text), Kosinus-Ähnlichkeit |
| `optimizer.py` | Schlägt Parameter-Änderungen vor; wendet sie nur nach Genehmigung an |
| `consent_log.py` | DSGVO-Protokoll jedes Außen-Kontakts (JSONL) |
| `metrics.py` | Nutzungs-/Ereignis-Metriken (JSONL) |
| `mcp_catalog.py` | Skill-Katalog: lädt `catalog/mcp.json` remote (24h-Cache, Fallback) |
| `mcp_client.py` | MCP-Stdio-JSON-RPC-Client; startet/verbindet Skill-Subprozesse |
| `model_catalog.py` | Modell-Katalog: lädt `catalog/models.json` remote |
| `principals.py` | Identitäten/Rechte (lokal, Matrix-Nutzer), `can_use_cloud` |
| `projects.py` | Projekte/Arbeits-Threads (Nachrichtenverläufe) |
| `scheduler.py` | Zeitgesteuerte Jobs |
| `settings.py` | Persistenz der GUI-Einstellungen (`user_settings.json`); Geheimnisse VERSCHLUESSELT (`_write`/`load`/`migrate_secrets`), `public()` maskiert |
| `secret_store.py` | Verschluesselung von Schluesseln at-rest: Windows DPAPI (ctypes, kein Dep), sonst `keyring`; `encrypt`/`decrypt`/`reveal`/`backend`. Token-Format `enc:dpapi:`/`enc:keyring:` |
| `runtimes.py` | Node/uv auffinden & installieren (`resolve`, `ensure`, `runtime_for_command`). Wird bei der Ersteinrichtung (`first_run`) UND bei `/mcp/install` automatisch aufgerufen, damit Skills ohne manuellen Schritt laufen |
| `sandbox.py` | `run_python` isoliert (Docker, sonst eingeschränkter Subprozess) |
| `local_servers.py` | Schnellstart alternativer lokaler Server (llamafile herunterladen+starten; GPT4All/LM Studio/Jan starten o. Download-Seite). Endpunkte `/local/servers`, `/local/launch`, `/local/launch/status` |
| `ollama_setup.py` | Ollama im Betrieb bereitstellen: `provision()` installiert (falls fehlt) bzw. aktualisiert (falls < 0.3.0 = kein Function-Calling), dann starten. Best effort/Hintergrund; `status()` in `/status`. Aufgerufen im Lifespan + in den Fehlerpfaden des Routers. Schalter `AUTO_INSTALL_OLLAMA`/`AUTO_UPDATE_OLLAMA` |
| `tailscale_setup.py` | Tailscale installieren/anmelden |
| `local_matrix.py` | Lokaler Matrix-Server (Conduit) via Docker |
| `extractor.py` | Inhalts-/Faktenextraktion (z.B. Gedächtnis-Vorschläge) |
| `connectors/matrix_connector.py` | Matrix-Client (E2EE, Auto-Join erlaubter Räume, `test_connection`) |
| `tools/registry.py` | Werkzeug-Registratur (`read_file`, `list_dir`, `run_python`, `web_search`) |

## 5. Anfrage-Fluss (`router.handle_task`)

1. `principal` bestimmen (lokal oder Messenger-Nutzer); Rechte prüfen.
2. Lokale KI (Ollama) bearbeitet die Aufgabe; ggf. Werkzeug-Schleife
   (`max_tool_steps`, Default 4). **Werkzeugaufruf:** bei Ollama **natives
   Function-Calling** (`local_llm.chat_tools` mit `tools`-Schema aus
   `Tool.parameters`/MCP-`inputSchema`; `router._native_call` liest `tool_calls`),
   sonst Rückfall auf JSON-im-Text (`_try_parse_tool_call`). Werkzeuge mit
   `requires_consent`/`leaves_device` lösen den Einwilligungs-Pfad aus.
3. Selbstbewertung < `CONFIDENCE_THRESHOLD` oder Fehlversuche > `MAX_LOCAL_RETRIES`:
   - Falls `AUTO_LOCAL_UPGRADE` und nicht `MODEL_LOCKED`: Autopilot versucht erst
     ein **größeres lokales** Modell (ggf. Hintergrund-Download).
   - Sonst `_cloud_or_block`: je nach `CLOUD_MODE`
     `off` → höflich blocken · `api` → Einwilligung für Cloud-Kette ·
     `browser` → Abo-Web-Chat öffnen (nur lokal/GUI), Frage in Zwischenablage.
4. Nach Einwilligung (`POST /consent`): `cloud_llm.chat()` läuft die Kette
   OpenRouter→Claude ab, protokolliert in `consent_log.jsonl`.

## 6. HTTP-Endpunkte (Auswahl, alle auf 127.0.0.1:8765)

- Kern: `GET /health`, `GET /status`, `GET /log`, `POST /chat`, `POST /consent`
- Projekte: `GET/POST /projects`, `POST /projects/{id}/activate`,
  `GET /projects/{id}/messages`, `DELETE /projects/{id}`
- Jobs/Scheduler: `GET/POST /jobs`
- Gedächtnis: `GET/POST /memory`, `DELETE /memory/{id}`,
  `POST /memory/suggest`, `POST /memory/dismiss`
- Optimierung: `GET /optimize/suggestions`, `POST /optimize/apply`
- Modelle: `GET /models`, `GET /models/catalog`, `POST /model/set`, `POST /model/pull`
- Skills (MCP): `GET /mcp`, `POST /mcp/servers`, `DELETE /mcp/servers/{name}`,
  `POST /mcp/reload`, `GET /mcp/catalog`, `POST /mcp/install`
- Runtimes: `GET /runtimes`, `POST /runtimes/install`
- Setup/Onboarding: `GET /setup/state`, `POST /setup/cloud-test`,
  `POST /setup/matrix-test`, `POST /setup/save`, `POST /settings`
- Netzwerk/Messenger: `GET /tailscale`, `POST /tailscale/install|login`,
  `GET /local-matrix`, `POST /local-matrix/start|stop`
- OAuth/Login: `POST /oauth/openrouter/start`, `GET /oauth/openrouter/callback`,
  `POST /ms365/login`

## 7. Einstellungen & Vorrang

Geltungsreihenfolge (jeweils überschreibend):
**Umgebungsvariablen-Defaults → `user_settings.json` (GUI) → `overrides.json` (Optimierer)**.
Alle Schlüssel: siehe `agent/config.py`. Vom Optimierer änderbar: nur `config._TUNABLE`
(`CONFIDENCE_THRESHOLD`, `MAX_LOCAL_RETRIES`, `LOCAL_MODEL`, `CLOUD_MODEL`,
`AUTO_LOCAL_UPGRADE`). GUI-Schlüssel werden in `config.apply_user_settings()` gemappt.
Menschlich erklärte Liste: [HANDBUCH.md](HANDBUCH.md) §„Einstellungen".

## 8. Datenablage (nutzerspezifisch, `config.data_dir()`)

Windows `%APPDATA%/PrivacyAgent`, macOS `~/Library/Application Support/PrivacyAgent`,
Linux `~/.local/share/PrivacyAgent`. Dateien:
`consent_log.jsonl`, `memories.jsonl`, `metrics.jsonl`, `overrides.json`,
`optimization_log.jsonl`, `autopilot.json`, `user_settings.json`,
`mcp_servers.json`, `projects.json`, `matrix/`,
`backend-start.log` (stdout/stderr des Sidecars beim Start -- erste Anlaufstelle
bei „Fenster bleibt leer/Verbinde"; von `src-tauri/src/main.rs` geschrieben).

Start der Tauri-Huelle: `spawn_backend()` startet das Sidecar nur, wenn auf
127.0.0.1:8765 noch keines lauscht (kein Doppelstart/Port-Konflikt). Die GUI zeigt
bis zur Backend-Erreichbarkeit einen Lade-Screen (`#loading`), nie ein schwarzes Fenster.

## 9. Kataloge (remote aktualisierbar)

- `catalog/models.json` — Ollama-Modelle; wöchentlich von
  `scripts/scrape_ollama.py` aus ollama.com/library aktualisiert
  (`.github/workflows/update-catalog.yml`).
- `catalog/mcp.json` — kuratierte Skill-Vorlagen (aktuell 17). Wird von der App
  remote nachgeladen (24h-Cache + Fallback). **Neue Skills hier ergänzen** →
  erscheinen ohne neuen Installer. Felder: `id, label, icon, description, command,
  args, env, params, needs, runtime` (+ optional `login: "ms365"` für den
  Microsoft-Login-Knopf). Platzhalter `{key}` in `args`/`env` werden durch
  Nutzereingaben ersetzt.

## 10. Konventionen für Änderungen

- **Sprache:** Nutzer-sichtbarer Text **Deutsch**. Code-Kommentare Deutsch,
  ASCII in Quelltext-Strings bevorzugt (Umlaute als `ae/oe/ue` in Kommentaren ok).
- **Encoding-Falle:** Subprozess-/Sidecar-Ausgabe für Rust **`ensure_ascii=True`**
  schreiben (sonst „stream did not contain valid UTF-8"). Siehe `setup/first_run.py`.
- **Windows-Subprozesse:** kein Konsolenfenster → `_proc.no_window()` verwenden.
- **Externe Programme** (npx/uvx/git/ollama) über `runtimes.resolve()` auflösen,
  nicht hart `"npx"` annehmen.
- **Neue Außen-Operation?** Zwingend `requires_consent`/`leaves_device` setzen und
  über den Einwilligungs-Pfad führen + `consent_log` schreiben.
- **Versionierung:** semantische Tags `vX.Y.Z`. Reine `catalog/*.json`-Änderungen
  wirken per Push (Remote-Nachladen); Code-Änderungen brauchen neuen Build.
- **Tests:** `test_agent.py` (Smoke). `python -m py_compile` vor Commit.

## 11. Build & Lauf (Kurz)

- Backend lokal: `python launcher.py` (oder `uvicorn agent.main:app`).
- Sidecar bauen: `python build_sidecar.py` (PyInstaller, `--collect-all` für
  certifi/requests u.a.).
- App/Installer: GitHub Actions `build.yml` (Tauri, Rust 1.88.0, pinned deps).
- Voraussetzungen Laufzeit: Ollama lokal; Node/uv werden bei Bedarf über
  `runtimes.install()` nachinstalliert (für MCP-Skills).
