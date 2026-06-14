# 🛡️ Privacy-Agent

Ein **eigenständiger KI-Agent**, der Aufgaben lokal und DSGVO-konform erledigt.
Die bezahlte Cloud-KI (Claude) wird **nur im Notfall und nur nach deiner
ausdrücklichen Rückfrage** genutzt. Plattformübergreifend (Windows / macOS /
Linux) als Desktop-App mit Doppelklick-Installer.

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
         └─ nur bei „Senden" → Claude API  ☁️  + DSGVO-Protokoll
```

Damit sind alle vier Anforderungen erfüllt:
1. **Eigenständig** – die lokale KI arbeitet autonom mit Werkzeugen.
2. **Cloud nur im Notfall** – Eskalation erst bei Unsicherheit/Fehler.
3. **Nur nach Rücksprache** – ausdrückliche Einwilligung pro Cloud-Aufruf.
4. **DSGVO-konform** – Standardbetrieb lokal; jeder Cloud-Aufruf wird protokolliert.

## Projektstruktur

| Pfad | Zweck |
|------|-------|
| `agent/` | **Python-Kern** (das „Gehirn") – sofort testbar |
| `agent/router.py` | Entscheidet: lokal lösen vs. Cloud-Eskalation |
| `agent/local_llm.py` | Anbindung an die lokale KI (Ollama) |
| `agent/cloud_llm.py` | Cloud-Notfall (Claude API, nur nach Einwilligung) |
| `agent/consent_log.py` | DSGVO-Protokoll jedes Cloud-Aufrufs |
| `agent/memory.py` | Persistentes **Gedächtnis** (Fakten, Vorlieben, Regeln) |
| `agent/embeddings.py` | Lokale Embeddings für die **semantische** Gedächtnissuche |
| `agent/extractor.py` | Schlägt merkenswerte Einträge automatisch aus Gesprächen vor |
| `agent/metrics.py` | Lokale Nutzungs-Telemetrie (Grundlage der Optimierung) |
| `agent/optimizer.py` | **Selbstoptimierung**: Vorschläge → Genehmigung → anwenden |
| `agent/autopilot.py` | Autonomer Wechsel auf ein **stärkeres lokales Modell** bei Schwierigkeiten |
| `agent/tools/` | Werkzeuge: Datei lesen, Code ausführen, Web-Suche |
| `agent/sandbox.py` | Gestufte **Sandbox** für `run_python` (Docker / OS-Limits) |
| `agent/mcp_client.py` | **MCP-Client**: importiert fremde Skills (Werkzeuge externer Server) |
| `agent/mcp_catalog.py` | Ein-Klick-Vorlagen beliebter MCP-Skills |
| `agent/runtimes.py` | Richtet **Node.js/uv** für Skills automatisch ein (ohne Admin) |
| `agent/connectors/` | **Messenger-Anbindung** (Matrix als Referenz, pluggbar) |
| `agent/main.py` | Lokaler HTTP-Server (FastAPI), verbindet GUI ↔ Kern |
| `setup/first_run.py` | Einrichtungs-Assistent: installiert Ollama + Modell |
| `ui/` | GUI (HTML/CSS/JS): Chat, Einwilligungs-Dialog, 🧠-Panel |
| `ui/wizard.js` | **Geführter Einrichtungs-Assistent** (für Laien, ohne `.env`) |
| `agent/settings.py` | Speichert die im Assistenten gewählten Einstellungen |
| `src-tauri/` | Tauri-Hülle (Rust): startet Backend, baut die Installer |

## Schnellstart (Entwicklung)

### 1. Nur den Agenten-Kern testen (ohne GUI)

```powershell
# Python-Abhängigkeiten
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r agent\requirements.txt

# Lokale KI bereitstellen (einmalig)
#   Ollama installieren: https://ollama.com  → dann:
ollama pull qwen2.5:7b

# Kern testen
python test_agent.py
```

Erwartung: Die Frage wird **lokal** beantwortet (Quelle `local`). Stelle die
Schwelle in `agent/config.py` hoch (z. B. `CONFIDENCE_THRESHOLD=11`), um die
**Eskalations-Rückfrage** zu provozieren.

### 2. Backend + GUI im Browser

```powershell
python -m agent.main          # Backend auf http://127.0.0.1:8765
# ui/index.html im Browser öffnen (oder Live-Server)
```

### 3. Volle Desktop-App (Tauri)

Voraussetzungen: [Node.js](https://nodejs.org), [Rust](https://rustup.rs),
[Tauri-Systemabhängigkeiten](https://tauri.app/start/prerequisites/).

Die Tauri-Hülle startet **kein** System-Python mehr, sondern ein gebündeltes
Backend-Binary (Sidecar). Dieses muss **vor** `npm run dev`/`build` erzeugt
werden:

```powershell
python build_sidecar.py    # erzeugt src-tauri/binaries/privacy-agent-backend-<triple>(.exe)
npm install
npm run dev                # startet Backend (Sidecar) + Fenster
npm run build              # erzeugt Installer in src-tauri/target/release/bundle/
```

## Cloud-Notfall aktivieren (optional)

Der lokale Betrieb braucht **keinen** Schlüssel. Für den Notfall:

```powershell
copy .env.example .env
# ANTHROPIC_API_KEY in .env eintragen
```

## Vom Skelett zum verteilbaren Produkt

Backend **und** Setup-Assistent stecken in einem einzigen Binary
([launcher.py](launcher.py) mit den Modi `serve`/`setup`), gebündelt per
PyInstaller. So braucht der Nutzer **kein** Python.

1. **Sidecar bauen:** `python build_sidecar.py` — erzeugt das Binary mit
   eingebettetem Python und legt es als Tauri-Sidecar unter
   `src-tauri/binaries/privacy-agent-backend-<triple>` ab.
   Das geschieht **pro Zielplattform** (auf einem Mac für macOS, usw.).
2. **Icons:** `python make_icons.py` (Pillow) **oder** `npm run icons`
   (`tauri icon app-icon.png`) erzeugt alle Icon-Formate aus `app-icon.png`.
3. `npm run build` erzeugt: `.exe`/NSIS (Windows), `.dmg` (macOS),
   `.AppImage`/`.deb` (Linux). Das Sidecar wird automatisch mit eingebettet.

> ⚠️ **Wichtig:** Modelle (2–20 GB) werden **nicht** in den Installer gepackt,
> sondern beim ersten Start vom Einrichtungs-Assistenten heruntergeladen.
> Der Installer bleibt dadurch klein (~80 MB).

### Automatische Builds (CI)

`.github/workflows/build.yml` baut die Installer für **alle drei Systeme**
automatisch – ein Job pro Betriebssystem (Cross-Compiling ist mit PyInstaller
nicht möglich, daher echte Runner). Jeder Job: Python/Node/Rust einrichten →
`build_sidecar.py` → `npm run icons` → `npm run build` → Installer als Artefakt
hochladen.

Ausgelöst wird er durch ein **Versions-Tag** oder manuell:

```bash
git tag v0.1.0 && git push origin v0.1.0   # baut Win/Mac/Linux-Installer
```

Die fertigen Installer liegen danach unter „Actions → der Lauf → Artifacts".

#### Code-Signing aktivieren (optional)

Standardmäßig sind die Installer **unsigniert** (Nutzer klicken einmal „Trotzdem
ausführen"). Der Workflow ist aber so vorbereitet, dass Signing sich **allein
über GitHub-Secrets** einschaltet – ohne Code-Änderung:

- **macOS** (Apple Developer, ~99 $/Jahr): Secrets `APPLE_CERTIFICATE` (Base64
  der `.p12`), `APPLE_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY` und – für
  Notarisierung – `APPLE_ID`, `APPLE_PASSWORD` (App-spezifisches Passwort),
  `APPLE_TEAM_ID`. Tauri signiert + notarisiert dann automatisch.
- **Windows**: Secrets `WINDOWS_CERTIFICATE` (Base64 der `.pfx`) und
  `WINDOWS_CERTIFICATE_PASSWORD`; zusätzlich einmalig in
  `src-tauri/tauri.conf.json` unter `bundle.windows` den `certificateThumbprint`
  des Zertifikats eintragen.
- **Linux**: kein Signing nötig.

Sind keine Secrets gesetzt, baut der Workflow ganz normal **unsigniert** weiter.
Secrets legst du an unter „Repo → Settings → Secrets and variables → Actions".

## Einrichtung ohne Vorkenntnisse (GUI-Assistent)

Beim **ersten Start** führt ein bebilderter Assistent (`ui/wizard.js`) in
einfacher Sprache durch alles – ganz **ohne `.env` oder Kommandozeile**:

1. **Willkommen** – kurze Begrüßung.
2. **KI aufs Gerät holen** – installiert die lokale KI (Fortschrittsbalken).
3. **Verhalten** – „Vorsichtig / Ausgewogen / Selbstständig" (setzt die
   Eskalations-Schwelle).
4. **Autopilot** – ein Schalter in Klartext.
5. **Cloud-Hilfe** (optional) – Schlüssel eingeben, **mit Test-Knopf**;
   überspringbar.
6. **Messenger** (optional) – Matrix einrichten **mit „Verbindung testen"-Knopf**
   (echter Anmeldeversuch, sofortiges ✅/❌); überspringbar.
7. **Fertig** – Zusammenfassung, dann „Loslegen".

Die Eingaben landen in `user_settings.json` (via `agent/settings.py`) und werden
**sofort aktiv** – Geheimnisse (API-Schlüssel, Passwörter) gibt die GUI nie im
Klartext zurück. Alles ist später im 🧠-Menü änderbar. Wer lieber per Datei
konfiguriert, kann weiterhin `.env` nutzen (Reihenfolge: `.env` < Assistent <
Optimierer).

## Lokales Modell wechseln (manuell & autonom)

**Manuell in der GUI** (🧠-Panel → „Lokales Modell"):
- Dropdown aller installierten Ollama-Modelle – Auswahl wechselt das aktive
  Modell **sofort im laufenden Prozess**.
- Feld zum Nachladen neuer Modelle (`ollama pull`, z. B. `mistral`).

**Autonom (Autopilot)** – `agent/autopilot.py`: Kommt die lokale KI bei einer
Aufgabe nicht weiter (niedrige Selbstsicherheit), versucht der Autopilot es
**zuerst mit einem stärkeren lokalen Modell**, bevor die Cloud vorgeschlagen
wird. Bewährt sich ein stärkeres Modell wiederholt (Standard: 3×), macht der
Agent es **autonom zum neuen Standard** (protokolliert in `optimization_log.jsonl`).

> 🔒 Autonom werden **nur lokale Open-Source-Modelle** gewechselt (kostenlos,
> auf dem Gerät, reversibel). Die **bezahlte Cloud** wird **nie** ohne deine
> ausdrückliche Einwilligung genutzt. Steuerbar per Schalter im 🧠-Panel
> bzw. `AUTO_LOCAL_UPGRADE` in `.env`. Das Antwort-Badge zeigt das genutzte
> Modell und „⬆ Autopilot", wenn hochgestuft wurde.

„Stärker" wird über die Parameterzahl bestimmt: zuerst aus dem Tag (`:14b`),
sonst aus einer kleinen Modell→Größe-Tabelle (`_MODEL_SIZES_B` in `autopilot.py`),
sodass auch größenlose Namen wie `mistral`, `mixtral` oder `llama3.3` korrekt
eingeordnet werden. Unbekannte Namen werden beim *automatischen* Upgrade
übersprungen (manuell bleiben sie wählbar) – Tabelle bei Bedarf erweitern.

Endpunkte: `GET /models`, `POST /model/set`, `POST /model/pull`, `POST /settings`.

## Gedächtnis & Selbstoptimierung

Der Agent merkt sich Dinge dauerhaft (lokal) und kann sich **auf Basis echter
Nutzungsdaten** selbst verbessern – jede Änderung jedoch nur nach deiner
Genehmigung.

**Gedächtnis** (`memory.py`, gespeichert als `memories.jsonl`):
- `fact` / `preference` – fließen bei passender Aufgabe in den System-Prompt ein.
- `guideline` – Betriebsregeln, die **immer** gelten.
- **Semantischer Abruf** über lokale Embeddings (`nomic-embed-text` via Ollama,
  ~270 MB, vom Einrichtungs-Assistenten mitinstalliert): findet Einträge nach
  Bedeutung, nicht nur nach Wortgleichheit – und erkennt so auch Synonyme.
- **Robuster Fallback:** Fehlt das Embedding-Modell, schaltet das Gedächtnis
  automatisch auf lexikalische Suche um – die App läuft trotzdem.
- Embeddings werden je Eintrag lokal gespeichert; Altbestand wird bei der ersten
  semantischen Suche automatisch nachgerüstet (Backfill).

**Automatische Vorschläge** (`extractor.py`): Nach jeder Antwort prüft die
**lokale** KI das Gespräch auf dauerhaft merkenswerte Fakten/Vorlieben und zeigt
sie als unaufdringliche „💡 Soll ich mir merken: …?"-Chips an – gespeichert wird
erst nach deinem Klick. **Im Messenger** läuft dasselbe als Chat-Dialog: der
Agent hängt den Vorschlag an seine Antwort, du antwortest mit **MERKEN** oder
**NEIN** – und es landet in **deinem eigenen** Gedächtnis-Bereich (Pro-Person). Duplikate (gegen Gespeichertes und innerhalb eines
Stapels, mit Stopwort-Filter) und in der Sitzung abgelehnte Vorschläge werden
herausgefiltert, damit es nicht nervt. Endpunkte: `POST /memory/suggest`,
`POST /memory/dismiss`.

**Selbstoptimierung** (`optimizer.py`): Aus der lokalen Telemetrie (`metrics.py`)
leitet der Agent konkrete Vorschläge ab, z. B.:
- Eskalations-Schwelle senken, wenn du die Cloud oft ablehnst.
- Stärkeres lokales Modell laden, wenn die lokale KI häufig nicht ausreicht.
- Qualitätsschwelle anheben, wenn lokale Antworten durchweg sicher sind.
- Eine Betriebsregel verankern (z. B. „zurückhaltend eskalieren").

> 🔒 **Sicherheitsgrenze (bewusst):** Der Agent schreibt **niemals** eigenen
> Quellcode um. Änderungen betreffen nur eine Whitelist umkehrbarer Stellen
> (getunte Parameter, Gedächtnis, Regeln). Jeder Schritt wird mit vorherigem
> Wert in `optimization_log.jsonl` protokolliert – nachvollziehbar und
> rückgängig machbar.

Bedienung in der App über das **🧠-Symbol** oben rechts: Vorschläge mit
*Übernehmen/Verwerfen* und das Gedächtnis verwalten.

Relevante Endpunkte: `GET /optimize/suggestions`, `POST /optimize/apply`,
`GET/POST /memory`, `DELETE /memory/{id}`.

## Messenger-Anbindung (Matrix, WhatsApp & Alternativen)

Der Agent kann über einen Messenger erreichbar gemacht werden – du chattest dann
aus der Ferne mit derselben lokalen „Brain"-Logik wie in der GUI, **inklusive
der Einwilligungs-Rückfrage**: Statt eines Buttons antwortest du im Chat mit
**JA / NEIN**.

**Matrix** (Referenz-Implementierung, empfohlen):
1. Auf deinem (privaten) Homeserver einen Account für den Agenten anlegen,
   z. B. `@agent:dein-server.de`, und den Agenten in einen Raum mit dir einladen.
2. In `.env` setzen: `CONNECTOR=matrix`, `MATRIX_HOMESERVER`, `MATRIX_USER`,
   `MATRIX_PASSWORD` (oder `MATRIX_ACCESS_TOKEN`) und – **wichtig** –
   `MATRIX_ALLOWED_USERS` mit deiner Matrix-ID.
3. Paket installieren: `pip install "matrix-nio[e2e]"` (das `[e2e]` aktiviert
   Ende-zu-Ende-Verschlüsselung; braucht `libolm`).
4. Backend starten – der Connector verbindet sich automatisch nach dem Start.

Am einfachsten geht das über den **GUI-Assistenten** (Schritt „Messenger"): dort
gibst du Server, Konto und Passwort ein und prüfst per **„Verbindung testen"**
sofort, ob es klappt (`POST /setup/matrix-test`). Nach dem Speichern startet der
Connector automatisch neu (`connectors.restart()`).

> 🔒 **Sicherheit:** Nur Nutzer aus `MATRIX_ALLOWED_USERS` dürfen den Agenten
> steuern; eine **leere** Liste bedeutet „niemand" (sicherer Standard).
> Alte Nachrichten (von vor dem Start) werden ignoriert. Mit privatem
> Homeserver + E2EE verlässt die Kommunikation deinen Bereich nicht.

### Pro-Person-Trennung

Mehrere Personen können denselben Agenten nutzen – sauber getrennt
(`agent/principals.py`):

- **Eigenes Gedächtnis je Person:** Jeder Matrix-Nutzer sieht nur sein eigenes
  Gedächtnis plus die als „shared" markierten Einträge (z. B. Betriebsregeln des
  Optimierers). Anna sieht Berts Notizen nicht. Verlauf und offene
  JA/NEIN-Rückfragen laufen ebenfalls pro Person – auch im selben Raum.
- **Eigene Berechtigungen:** `MATRIX_ADMIN_USERS` (bzw. das Feld im Assistenten)
  legt fest, **wer die kostenpflichtige Cloud freigeben darf**. Nicht
  berechtigte Personen bleiben rein lokal – kommt die lokale KI nicht weiter,
  bekommen sie eine freundliche Absage statt einer Cloud-Rückfrage. Leere Liste
  = alle erlaubten Personen dürfen es (abwärtskompatibel).

Der lokale GUI-Nutzer ist ein vollberechtigter Principal mit eigenem Bereich
(`local`).

### Praxisbeispiel: Synapse auf einem NAS über Tailscale

Ein typisches privates Setup – Matrix-Homeserver (Synapse) läuft als Docker-
Container auf einem NAS, erreichbar nur im eigenen Tailscale-Netz unter einer
MagicDNS-Adresse wie `nas.dein-tailnet.ts.net`.

**1. Server-Begriffe auseinanderhalten**

- **`server_name`** = der Teil **nach dem Doppelpunkt** in jeder Nutzer-ID
  (`@name:server_name`). Steht in der `homeserver.yaml` und ist beim ersten
  Start festgelegt – nicht nachträglich ändern.
- **Server-Adresse / Homeserver-URL** = wo der Client sich verbindet
  (NAS + Port). Beides darf unterschiedlich sein.

`server_name` prüfen (Container-Name ggf. anpassen, via `docker ps` ermitteln):

```bash
docker exec matrix-synapse grep "server_name" /data/homeserver.yaml
```

**2. Zwei Konten anlegen** – auf dem NAS (z. B. per `ssh DEIN-NUTZER@nas.dein-tailnet.ts.net`):

```bash
docker exec -it matrix-synapse \
  register_new_matrix_user -c /data/homeserver.yaml http://localhost:8008
```

Der Befehl fragt interaktiv nach `localpart` (Name), Passwort und „Make admin".
Einmal für den **Agenten** (Admin: nein) und einmal für **dich** (Admin: ja).
Ziel ist jeweils die Meldung `Success!`. (`http://localhost:8008` ist Synapse
*im Container* – unabhängig von Tailscale.)

> Fehler `Shared secret registration is not enabled`? Dann in der
> `homeserver.yaml` eine Zeile `registration_shared_secret: "<zufällig>"`
> ergänzen und `docker restart <container>`.

**3. Werte in den GUI-Assistenten** (Beispiel: Agent `agent`, du `max`,
`server_name` = `nas.dein-tailnet.ts.net`, Port `8008` nach außen freigegeben):

| Feld im Assistenten | Wert |
|---|---|
| Server-Adresse | `http://nas.dein-tailnet.ts.net:8008` |
| Agenten-Konto | `@agent:nas.dein-tailnet.ts.net` |
| Passwort | Passwort des **Agenten**-Kontos (`agent`) |
| Deine Matrix-Adresse | `@max:nas.dein-tailnet.ts.net` |

Dann **„Verbindung testen"** → `✅`. Schöner mit gültigem HTTPS:
`tailscale serve --bg 8008` auf dem NAS, dann `https://nas.dein-tailnet.ts.net`.

**4. Einmalig in Element:** mit **deinem** Konto anmelden (Homeserver dieselbe
Adresse), einen Raum erstellen und das **Agenten-Konto einladen**. In diesem
Raum schreibst du dem Agenten.

> Voraussetzungen: Der Agent-PC muss **im selben Tailnet** sein
> (`ping nas.dein-tailnet.ts.net`), und `pip install "matrix-nio[e2e]"` muss
> installiert sein.

**WhatsApp – ehrliche Einordnung:** WhatsApp hat **keine** datenschutzfreundliche
lokale Schnittstelle. Die offizielle *Business Cloud API* leitet Nachrichten über
Meta-Server (Konflikt mit dem Local-First-/DSGVO-Ziel), inoffizielle Bibliotheken
verstoßen gegen die Nutzungsbedingungen. Der saubere Weg ist eine **Matrix-Bridge**
(z. B. `mautrix-whatsapp`): Die Bridge läuft auf *deinem* Server und verbindet
WhatsApp mit deinem Matrix-Raum – der Agent spricht weiterhin nur Matrix und
bleibt unverändert. Genauso lassen sich Signal, Telegram & Co. anbinden.

**Eigene Connectoren:** Das Paket `agent/connectors/` ist pluggbar – ein neuer
Messenger braucht nur eine Klasse mit `async run()`, die eingehende Nachrichten
an `connectors.session.Conversations.process()` weiterreicht. Die gesamte
Gesprächs- und Einwilligungs-Logik ist dort schon gekapselt.

## Fremde Skills importieren (MCP)

Der Agent kann Werkzeuge **externer Anbieter** über das **Model Context Protocol
(MCP)** nutzen – der heutige Standard für Agenten-Tools (Dateisystem, GitHub,
Suche, Datenbanken …). `agent/mcp_client.py` startet konfigurierte MCP-Server
als Subprozesse, listet deren Werkzeuge und registriert sie automatisch als
Werkzeuge des Agenten (Name: `mcp__<server>__<tool>`). Das lokale Modell kann
sie dann wie eigene Werkzeuge aufrufen.

**Ein-Klick-Vorlagen** (`mcp_catalog.py`): Im 🧠-Panel unter „Externe Skills"
gibt es Vorlagen für beliebte Skills – **Dateien**, **GitHub**, **Websuche**
(Brave) und **Webseite abrufen**. Ein Klick, höchstens noch ein Ordner oder
Schlüssel eingeben, fertig (Endpunkte `GET /mcp/catalog`, `POST /mcp/install`).
Wer mag, fügt eigene Server weiter manuell hinzu.

**Automatische Laufzeit-Einrichtung** (`runtimes.py`): MCP-Skills brauchen oft
Node.js (`npx`) oder uv (`uvx`). Fehlt das, bietet die GUI direkt im Vorlagen-
Dialog ein **„automatisch einrichten"** an – Node.js wird als vorgefertigtes
Archiv **ohne Admin-Rechte** in `<Daten>/runtimes/node` entpackt, uv über den
offiziellen Installer. Der MCP-Client findet die Befehle dann automatisch
(System-PATH oder verwalteter Ort). Endpunkte: `GET /runtimes`,
`POST /runtimes/install`.

**Konfiguration** – im 🧠-Panel unter „Externe Skills" (Vorlage oder manuell:
Name, Befehl, Argumente) oder direkt in `mcp_servers.json` (auch das
`mcpServers`-Format von Claude Desktop wird gelesen):

```json
{ "servers": [
  { "name": "dateien", "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/pfad"],
    "trust": false }
] }
```

> 🔒 **Sicherheit:** Fremde Skills sind fremder Code. Sie werden standardmäßig
> als `requires_consent` registriert – **vor jedem Aufruf** kommt die
> Einwilligungs-Rückfrage (Werkzeugname + Argumente werden gezeigt). Nur mit
> `"trust": true` entfällt sie. Endpunkte: `GET /mcp`, `POST /mcp/servers`,
> `DELETE /mcp/servers/{name}`, `POST /mcp/reload`.

## DSGVO-Hinweise

- **Datenminimierung:** Standardbetrieb komplett lokal – keine Auftrags-
  verarbeitung nötig.
- **Einwilligung:** Die Ja/Nein-Rückfrage vor jedem Cloud-Aufruf ist die
  dokumentierte Einwilligung.
- **Rechenschaft (Art. 5 DSGVO):** Jeder Cloud-Aufruf landet im Protokoll
  (`consent_log.jsonl` im Nutzer-Datenordner).
- **Bei produktivem Cloud-Einsatz:** Mit Anthropic einen Auftragsverarbeitungs-
  vertrag (AVV/DPA) abschließen.

## Code-Sandbox (`run_python`)

Agenten-generierter Code wird **nicht ungeschützt** ausgeführt:

1. **Genehmigungspflicht:** `run_python` ist `requires_consent` – vor jeder
   Ausführung erscheint der Einwilligungs-Dialog mit dem konkreten Code.
2. **Gestufte Isolation** (`agent/sandbox.py`) – die stärkste verfügbare Stufe:
   - **Docker** (empfohlen): eigener Container **ohne Netzwerk**, Speicher-/CPU-/
     Prozesslimit, read-only Dateisystem, `cap-drop ALL`, `no-new-privileges`,
     non-root. Starke Isolation für nicht vertrauenswürdigen Code.
   - **Subprozess** (Fallback): isoliertes Temp-Verzeichnis, bereinigte Umgebung,
     Zeitlimit. POSIX zusätzlich harte `resource`-Limits; **Windows** via
     **Job Object** mit Speicher-/Prozesslimit und garantiertem Aufräumen.

Das Werkzeug-Ergebnis nennt die verwendete Stufe (`[Sandbox: Docker]` /
`[Sandbox: eingeschränkt]`), sodass transparent bleibt, wie stark isoliert wurde.

> ⚠️ Die Subprozess-Stufe ist **keine** vollständige Isolation (u. a. ist der
> Netzwerkzugriff nicht zuverlässig unterbunden). Für nicht vertrauenswürdigen
> Code Docker installieren – dann wird automatisch die Docker-Stufe genutzt.
> Tipp: `docker pull python:3.12-slim` vorab, damit offline kein Pull nötig ist.

Feinjustierung über `.env`: `SANDBOX_BACKEND` (auto|docker|subprocess),
`SANDBOX_IMAGE`, `SANDBOX_TIMEOUT`, `SANDBOX_MEM_MB`.
```
