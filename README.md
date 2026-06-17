# 🛡️ Privacy-Agent

Ein **eigenständiger KI-Agent**, der Aufgaben lokal und DSGVO-konform erledigt.
Die bezahlte Cloud-KI wird **nur im Notfall und nur nach deiner ausdrücklichen
Rückfrage** genutzt. Plattformübergreifend (Windows / macOS / Linux) als
Desktop-App mit Doppelklick-Installer.

## 📖 Welche Doku brauchst du?

| Du bist … | Lies … |
|---|---|
| **Nutzer:in** (Bedienung, alle Einstellungen, FAQ) | 👉 **[HANDBUCH.md](HANDBUCH.md)** |
| **KI-Coding-Agent / Entwickler:in** (Architektur, Module, Invarianten, Endpunkte) | 👉 **[AGENTS.md](AGENTS.md)** |
| Du willst das Projekt **bauen/verteilen** | weiter unten in dieser Datei |

> Damit es keine Doppelpflege gibt, stehen Bedien- und Architekturdetails **nur**
> in HANDBUCH.md / AGENTS.md. Diese README ist die Schnellstart- und Build-Seite.

## Grundidee

```
Aufgabe
   │
   ▼
[ Lokale KI (Ollama) + Werkzeuge ]   ← läuft komplett auf dem Gerät, DSGVO-konform
   │
   ├─ sicher gelöst ─────────────────►  Antwort  🔒
   │
   └─ unsicher / Fehler / Internet nötig
         │
         ▼
   ┌──────────────────────────────────────────────┐
   │  Rückfrage (GUI-Dialog):                      │
   │  „Lokal nicht lösbar. Folgende Daten würden   │
   │   gesendet: […]"   [Lokal bleiben] [Senden]   │
   └──────────────────────────────────────────────┘
         │
         └─ nur bei „Senden" → Cloud-Kette  ☁️  + DSGVO-Protokoll
```

Eskalation in fester Reihenfolge: **lokal → größeres lokales Modell (Autopilot)
→ OpenRouter → Claude** – die letzten beiden Stufen nur nach Einwilligung.

1. **Eigenständig** – die lokale KI arbeitet autonom mit Werkzeugen.
2. **Cloud nur im Notfall** – Eskalation erst bei Unsicherheit/Fehler.
3. **Nur nach Rücksprache** – ausdrückliche Einwilligung pro Cloud-Aufruf.
4. **DSGVO-konform** – Standardbetrieb lokal; jeder Cloud-Aufruf wird protokolliert.

## Funktionsüberblick

Details und Bedienung jeweils im **[HANDBUCH.md](HANDBUCH.md)**:

- 🧠 **Gedächtnis** mit semantischer Suche + automatische Merk-Vorschläge (pro Person getrennt)
- ⚙️ **Selbstoptimierung** – Vorschläge nur nach Genehmigung, nie am Quellcode
- 🚀 **Autopilot** – autonomer Wechsel auf ein stärkeres *lokales* Modell (+ Auto-Download)
- 🧩 **Skills (MCP)** – 17 Ein-Klick-Vorlagen (Dateien, Websuche, Browser, **Outlook/Gmail**, Kalender …)
- 💬 **Messenger (Matrix)** – Fernsteuerung inkl. Einwilligung per Chat; Tailscale-Anbindung
- 🛡️ **Code-Sandbox** für `run_python` (Docker / OS-Limits), genehmigungspflichtig

## Projektstruktur (Kurzüberblick)

| Pfad | Zweck |
|------|-------|
| `agent/` | **Python-Kern** (FastAPI-Backend, „Gehirn") – vollständige Modul-Landkarte in [AGENTS.md](AGENTS.md) |
| `ui/` | GUI (HTML/CSS/JS): Chat, Einwilligungs-Dialog, 🧠-Panel, Einrichtungs-Assistent |
| `setup/first_run.py` | Einrichtungs-Assistent: installiert Ollama + Modell beim ersten Start |
| `catalog/` | Remote nachladbare Kataloge: `models.json` (Ollama-Modelle), `mcp.json` (Skills) |
| `src-tauri/` | Tauri-Hülle (Rust): startet das Backend-Sidecar, baut die Installer |
| `launcher.py` / `build_sidecar.py` | Sidecar-Einstieg (Modi serve/setup) + PyInstaller-Bündelung |
| `scripts/scrape_ollama.py` | Wöchentlicher Scraper, der `catalog/models.json` aktualisiert |

## Schnellstart (Entwicklung)

### 1. Nur den Agenten-Kern testen (ohne GUI)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r agent\requirements.txt

# Lokale KI bereitstellen (einmalig): Ollama von https://ollama.com, dann:
ollama pull qwen2.5:7b

python test_agent.py
```

Erwartung: Die Frage wird **lokal** beantwortet (Quelle `local`). Setze in
`agent/config.py` `CONFIDENCE_THRESHOLD=11`, um die **Eskalations-Rückfrage** zu provozieren.

### 2. Backend + GUI im Browser

```powershell
python -m agent.main          # Backend auf http://127.0.0.1:8765
# ui/index.html im Browser öffnen (oder Live-Server)
```

### 3. Volle Desktop-App (Tauri)

Voraussetzungen: [Node.js](https://nodejs.org), [Rust](https://rustup.rs),
[Tauri-Systemabhängigkeiten](https://tauri.app/start/prerequisites/).

Die Tauri-Hülle startet **kein** System-Python, sondern ein gebündeltes
Backend-Binary (Sidecar). Dieses muss **vor** `npm run dev`/`build` erzeugt werden:

```powershell
python build_sidecar.py    # erzeugt src-tauri/binaries/privacy-agent-backend-<triple>(.exe)
npm install
npm run dev                # startet Backend (Sidecar) + Fenster
npm run build              # erzeugt Installer in src-tauri/target/release/bundle/
```

## Build & Verteilung

Backend **und** Setup-Assistent stecken in einem einzigen Binary
([launcher.py](launcher.py), Modi `serve`/`setup`), gebündelt per PyInstaller –
der Nutzer braucht **kein** Python.

1. **Sidecar bauen:** `python build_sidecar.py` → Binary unter
   `src-tauri/binaries/privacy-agent-backend-<triple>` (**pro Zielplattform**,
   Cross-Compiling ist mit PyInstaller nicht möglich).
2. **Icons:** `python make_icons.py` **oder** `npm run icons` (`tauri icon app-icon.png`).
3. `npm run build` erzeugt `.exe`/NSIS (Windows), `.dmg` (macOS),
   `.AppImage`/`.deb` (Linux). Das Sidecar wird automatisch eingebettet.

> ⚠️ Modelle (2–20 GB) werden **nicht** in den Installer gepackt, sondern beim
> ersten Start heruntergeladen – so bleibt der Installer klein (~80 MB).

### Automatische Builds (CI)

`.github/workflows/build.yml` baut die Installer für alle drei Systeme (ein Job
pro OS: Python/Node/Rust → `build_sidecar.py` → `npm run icons` → `npm run build`
→ Installer als Artefakt). Ausgelöst durch ein **Versions-Tag** oder manuell:

```bash
git tag v0.2.26 && git push origin v0.2.26   # baut Win/Mac/Linux-Installer
```

Fertige Installer: „Actions → der Lauf → Artifacts". Der zweite Workflow
`update-catalog.yml` aktualisiert wöchentlich `catalog/models.json`.

> **Kataloge wirken ohne Build:** Reine Änderungen an `catalog/*.json` (neue
> Skills/Modelle) erscheinen in der App per Remote-Nachladen (↻ / täglich) –
> nur Code-/GUI-Änderungen brauchen einen neuen Installer.

### Code-Signing aktivieren (optional)

Standardmäßig sind die Installer **unsigniert**. Signing schaltet sich **allein
über GitHub-Secrets** ein (kein Code-Änderung nötig):

- **macOS** (Apple Developer): `APPLE_CERTIFICATE` (Base64 `.p12`),
  `APPLE_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY` und für Notarisierung
  `APPLE_ID`, `APPLE_PASSWORD`, `APPLE_TEAM_ID`.
- **Windows**: `WINDOWS_CERTIFICATE` (Base64 `.pfx`), `WINDOWS_CERTIFICATE_PASSWORD`;
  zusätzlich `certificateThumbprint` in `src-tauri/tauri.conf.json` unter `bundle.windows`.
- **Linux**: kein Signing nötig.

Ohne Secrets baut der Workflow normal unsigniert weiter. Secrets unter
„Repo → Settings → Secrets and variables → Actions".

## Praxisanleitung: Synapse auf einem NAS über Tailscale

<details>
<summary>Privates Matrix-Setup (Synapse im Docker auf einem NAS, erreichbar nur im Tailnet) – aufklappen</summary>

Matrix-Homeserver (Synapse) als Docker-Container auf einem NAS, erreichbar nur im
eigenen Tailscale-Netz unter einer MagicDNS-Adresse wie `nas.dein-tailnet.ts.net`.

**1. Server-Begriffe auseinanderhalten**

- **`server_name`** = der Teil **nach dem Doppelpunkt** in jeder Nutzer-ID
  (`@name:server_name`). Steht in der `homeserver.yaml`, beim ersten Start
  festgelegt – nicht nachträglich ändern.
- **Server-Adresse / Homeserver-URL** = wo der Client sich verbindet (NAS + Port).

`server_name` prüfen (Container-Name via `docker ps` ermitteln):

```bash
docker exec matrix-synapse grep "server_name" /data/homeserver.yaml
```

**2. Zwei Konten anlegen** – auf dem NAS (z. B. `ssh DEIN-NUTZER@nas.dein-tailnet.ts.net`):

```bash
docker exec -it matrix-synapse \
  register_new_matrix_user -c /data/homeserver.yaml http://localhost:8008
```

Interaktiv nach Name, Passwort und „Make admin" gefragt – einmal für den
**Agenten** (Admin: nein), einmal für **dich** (Admin: ja). Ziel: `Success!`.

> Fehler `Shared secret registration is not enabled`? In der `homeserver.yaml`
> `registration_shared_secret: "<zufällig>"` ergänzen und Container neu starten.

**3. Werte in den GUI-Assistenten** (Beispiel: Agent `agent`, du `max`,
`server_name` = `nas.dein-tailnet.ts.net`, Port `8008` freigegeben):

| Feld im Assistenten | Wert |
|---|---|
| Server-Adresse | `http://nas.dein-tailnet.ts.net:8008` |
| Agenten-Konto | `@agent:nas.dein-tailnet.ts.net` |
| Passwort | Passwort des **Agenten**-Kontos (`agent`) |
| Deine Matrix-Adresse | `@max:nas.dein-tailnet.ts.net` |

Dann **„Verbindung testen"** → `✅`. Schöner mit gültigem HTTPS:
`tailscale serve --bg 8008` auf dem NAS, dann `https://nas.dein-tailnet.ts.net`.

**4. Einmalig in Element:** mit **deinem** Konto anmelden (gleiche Adresse),
einen Raum erstellen und das **Agenten-Konto einladen**. Dort schreibst du dem Agenten.

> Voraussetzungen: Der Agent-PC muss **im selben Tailnet** sein
> (`ping nas.dein-tailnet.ts.net`), und `pip install "matrix-nio[e2e]"` installiert sein.

**WhatsApp & Co.:** WhatsApp hat keine datenschutzfreundliche lokale
Schnittstelle. Der saubere Weg ist eine **Matrix-Bridge** (z. B.
`mautrix-whatsapp`) auf deinem Server – der Agent spricht weiterhin nur Matrix.

</details>

## DSGVO-Hinweise

- **Datenminimierung:** Standardbetrieb komplett lokal.
- **Einwilligung:** Die Ja/Nein-Rückfrage vor jedem Cloud-Aufruf ist die dokumentierte Einwilligung.
- **Rechenschaft (Art. 5 DSGVO):** Jeder Cloud-Aufruf landet im Protokoll
  (`consent_log.jsonl` im Nutzer-Datenordner).
- **Bei produktivem Cloud-Einsatz:** Mit dem Anbieter einen Auftragsverarbeitungs-
  vertrag (AVV/DPA) abschließen.
