# Privacy-Agent — Handbuch für Menschen

Ein **persönlicher KI-Assistent, der zuerst auf deinem eigenen Computer denkt** –
mit einer lokalen, kostenlosen Open-Source-KI. Das Internet/die bezahlte Cloud
wird **nur im Notfall und nur mit deiner ausdrücklichen Erlaubnis** genutzt.
Deine Daten bleiben standardmäßig bei dir.

> Technische Fassung für KI-/Entwickler: siehe [AGENTS.md](AGENTS.md).

---

## Inhalt
1. [Was der Agent kann](#1-was-der-agent-kann)
2. [Wie er „denkt" — die Reihenfolge](#2-wie-er-denkt--die-reihenfolge)
3. [Installation & erster Start](#3-installation--erster-start)
4. [Alle Einstellungen im Detail](#4-alle-einstellungen-im-detail)
5. [Skills (externe Fähigkeiten)](#5-skills-externe-fähigkeiten)
6. [Messenger: den Agenten per Matrix steuern](#6-messenger-den-agenten-per-matrix-steuern)
7. [Wo deine Daten liegen](#7-wo-deine-daten-liegen)
8. [Häufige Fragen](#8-häufige-fragen)

---

## 1. Was der Agent kann

- **Fragen beantworten & Aufgaben erledigen** mit lokaler KI (Ollama).
- **Gedächtnis:** merkt sich auf Wunsch Fakten über dich/deine Arbeit – getrennt
  pro Person. Schlägt selbst Gedächtnis-Einträge vor.
- **Selbstoptimierung:** schlägt Verbesserungen seiner Einstellungen vor – ändert
  aber nur nach deiner Genehmigung (nie am Quellcode).
- **Skills nachrüsten:** z.B. Dateien lesen, Websuche, Wikipedia, Browser steuern,
  **Outlook/Gmail**, Kalender – per Ein-Klick-Vorlage.
- **Per Messenger erreichbar** (Matrix), auch von unterwegs über ein privates Netz
  (Tailscale).
- **Autopilot:** wählt bei schwierigen Aufgaben selbstständig ein stärkeres lokales
  Modell (und lädt es bei Bedarf herunter) – sofern nicht gesperrt.

## 2. Wie er „denkt" — die Reihenfolge

```
1.  Lokale KI auf deinem PC        →  kostenlos, privat, immer zuerst
       ↓  reicht nicht?
2.  Größeres lokales Modell        →  Autopilot (falls erlaubt), noch immer lokal
       ↓  reicht immer noch nicht?
3.  Nachfrage an dich  →  Erst nach deinem „OK" geht etwas nach außen:
       a) OpenRouter   →  günstig, ein Login für viele Modelle
       b) Claude       →  letzte Stufe (Anthropic)
```

**Wichtig:** Schritt 3 passiert **nie automatisch** ohne deine Zustimmung, und jeder
Außen-Kontakt wird protokolliert (nachlesbar).

## 3. Installation & erster Start

1. Installer ausführen (Windows/macOS/Linux).
2. Beim ersten Start führt dich ein **Assistent** durch alles: Er prüft/installiert
   die lokale KI (Ollama), wählt anhand deiner Hardware ein passendes Modell und
   lädt es herunter.
3. Optional: Cloud-Notfall, Messenger, Skills einrichten (alles auch später möglich).

Du brauchst **keine Technik-Kenntnisse** – alle Einstellungen sind in der Oberfläche.

## 4. Alle Einstellungen im Detail

### 4.1 Lokale KI
| Einstellung | Bedeutung | Empfehlung |
|---|---|---|
| **Lokaler Motor** (`local_backend`) | `Ollama` (Standard – installiert & verwaltet Modelle, GPU-Erkennung) **oder** ein eigener **OpenAI-kompatibler Server** (llama.cpp `llama-server`, **llamafile**, LM Studio, Jan). Mit der zweiten Option läuft der Agent **ganz ohne Ollama**. | Ollama, außer du willst es bewusst schlank. |
| **Server-Adresse** (`local_openai_base_url`) | Nur bei „eigener Server": URL inkl. `/v1`, z.B. `http://127.0.0.1:8080/v1`. Knopf **„Speichern & testen"** prüft die Erreichbarkeit. | – |
| **Lokales Modell** | Welches Open-Source-Modell antwortet (z.B. `qwen2.5:7b`). | Vom Assistenten passend zur Hardware gewählt. |
| **Autopilot: stärkeres Modell** (`auto_local_upgrade`) | Bei schwierigen Aufgaben selbst auf ein größeres lokales Modell wechseln. | **An** – bleibt kostenlos & lokal. |
| **Modelle selbst herunterladen** (`auto_download_models`) | Darf der Autopilot fehlende, größere Modelle im Hintergrund laden? | An, wenn genug Speicher/Bandbreite da ist. |
| **Modell-Sperre** (`model_locked`) | Wenn an, ändert **nur du** das Modell – der Agent fasst es nicht an. | An, wenn du ein festes Modell willst. |

> Hinweis: Mit dem Motor „eigener Server" entfallen **Auto-Download**, **Autopilot**
> und der **Modell-Katalog** (die hängen an Ollama). Du stellst dann Modell und
> Server selbst bereit.
>
> **Schnellauswahl + Starten:** Wähle in der Liste deinen Server (GPT4All, LM Studio,
> Jan, llamafile) – die Adresse wird automatisch eingetragen. Der Knopf **„Starten"**:
> - **llamafile:** lädt beim ersten Mal automatisch eine kleine KI-Datei herunter
>   und startet sie – **vollautomatisch, ohne Ollama**.
> - **GPT4All / LM Studio / Jan:** startet die App, falls installiert (LM Studio sogar
>   den API-Server direkt); sonst öffnet sich die Download-Seite. Bei GPT4All/Jan musst
>   du den **API-Server einmalig in der App aktivieren** (Einstellungen).

### 4.2 Cloud-Notfall (geht nur nach Einwilligung)
| Einstellung | Optionen | Bedeutung |
|---|---|---|
| **Notfall-Modus** (`cloud_mode`) | `off` / `api` / `browser` | `off` = nie Cloud (rein lokal). `api` = Cloud-KI per Schlüssel (nach OK). `browser` = öffnet das Web-Chat **deines Abos** und legt die Frage in die Zwischenablage (nur direkt am PC). |
| **Anbieter-Kette** (`cloud_provider`) | **Automatisch** / **Nur Claude** | „Automatisch" (empfohlen): nutzt **jeden hinterlegten Schlüssel** automatisch, Reihenfolge **OpenRouter → Mistral → Claude** mit Rückfall. Hast du z.B. nur einen Mistral-Schlüssel, nimmt er Mistral. |
| **OpenRouter-Login** | Knopf „Mit OpenRouter anmelden" | Ein Login → viele Modelle. Kein Schlüssel tippen (OAuth). |
| **OpenRouter-Modell** (`openrouter_model`) | z.B. `openrouter/auto` | `auto` wählt automatisch ein passendes Modell. |
| **Mistral-Schlüssel** (`mistral_api_key`) | API-Schlüssel | Mistral AI als Cloud-Stufe (von console.mistral.ai). Wird in „Automatisch" mitgenutzt. |
| **Claude/Anthropic-Schlüssel** (`anthropic_api_key`) | API-Schlüssel | Claude als letzte Stufe (oder „Nur Claude"). |
| **Abo im Browser** (`browser_provider`) | `claude` / `chatgpt` / `gemini` | Welches Web-Chat im `browser`-Modus geöffnet wird. |

> Hinweis: Ein Abo-Login (claude.ai usw.) lässt sich **nicht** als API verwenden
> (Nutzungsbedingungen). Dafür gibt es den `browser`-Modus oder OpenRouter.

### 4.3 Entscheidungs-Stil & Schwellen
| Einstellung | Bedeutung |
|---|---|
| **Entscheidungs-Stil** (`decision_style`) | `cautious` (vorsichtig, fragt früher nach), `balanced` (ausgewogen), `autonomous` (eigenständiger). Setzt intern die Sicherheits-Schwelle. |
| **Sicherheits-Schwelle** (`CONFIDENCE_THRESHOLD`, 0–10) | Unter diesem Selbst-Vertrauen schlägt er Eskalation vor. |
| **Lokale Wiederholungen** (`MAX_LOCAL_RETRIES`) | Wie oft lokal erneut versucht wird, bevor eskaliert wird. |

### 4.4 Gedächtnis
| Einstellung | Bedeutung |
|---|---|
| **Duplikat-Schwelle** (`SEMANTIC_DUP_THRESHOLD`) | Ab welcher Ähnlichkeit zwei Einträge als dasselbe gelten. |
| **Relevanz-Schwelle** (`SEMANTIC_MIN_SIM`) | Ab welcher Ähnlichkeit ein Eintrag bei der Suche genutzt wird. |
| **Embedding-Modell** (`EMBED_MODEL`) | Kleines lokales Modell für die Bedeutungs-Suche (Standard `nomic-embed-text`). |

### 4.5 Code-Sandbox (Werkzeug „Python ausführen")
| Einstellung | Bedeutung |
|---|---|
| **Backend** (`SANDBOX_BACKEND`) | `auto` (Docker falls vorhanden, sonst eingeschränkter Subprozess), `docker`, `subprocess`. |
| **Zeitlimit** (`SANDBOX_TIMEOUT`) | Max. Sekunden pro Ausführung. |
| **Speicherlimit** (`SANDBOX_MEM_MB`) | Max. Arbeitsspeicher (MB). |

### 4.6 Messenger (Matrix)
| Einstellung | Bedeutung |
|---|---|
| **Connector** (`connector`) | `none` oder `matrix`. |
| **Homeserver / Nutzer / Passwort oder Token** | Zugang des Agenten-Kontos. |
| **Erlaubte Nutzer** (`matrix_allowed_users`) | Nur diese dürfen den Agenten steuern. **Leer = niemand.** |
| **Admin-Nutzer** (`matrix_admin_users`) | Nur diese dürfen die bezahlte Cloud freigeben. Leer = alle erlaubten. |

## 5. Skills (externe Fähigkeiten)

Unter **Skills** wählst du aus fertigen Vorlagen (aktuell 17), z.B.:

- 📁 Dateien · 🌐 Webseite abrufen · 🔎/🦆/🔍 Websuche (Brave/DuckDuckGo/Tavily) ·
  📚 Wikipedia · 🎭 Browser steuern · 🐙 GitHub · 🗺️ Google Maps · 🗄️ SQLite ·
  🌿 Git · 🧠 Wissensgraph · 🕒 Zeit · 🧩 Schritt-für-Schritt-Denken
- 📧 **Outlook E-Mail** & ✉️ **Gmail** (per App-Passwort)
- 📨 **Outlook (Login)** – Mail **und** Kalender über Microsoft-Anmeldung
  (Knopf „Mit Microsoft anmelden", kein App-Passwort nötig)

Manche Skills brauchen **Node** oder **uv**. Diese **Laufzeiten richtet die App
automatisch ein** – schon bei der Ersteinrichtung und spätestens, wenn du einen
Skill hinzufügst (ohne Admin-Rechte, in den App-Datenordner). Beim **ersten** Mal
lädt ein Skill sein Paket zusätzlich aus dem Netz – das kann etwas dauern; falls
„nicht verbunden" erscheint, hilft der Knopf **„↻ neu verbinden"**.

Skills, die Daten nach außen geben, fragen vorher um Erlaubnis (außer du setzt
bewusst „Vertrauen – ohne Rückfrage").

## 6. Messenger: den Agenten per Matrix steuern

1. Connector auf **Matrix** stellen, Agenten-Konto eintragen (Server, Nutzer,
   Passwort/Token).
2. Unter **Erlaubte Nutzer** deine Matrix-ID eintragen (z.B. `@max:dein-server`).
3. Optional: **Tailscale** installieren/anmelden, um sicher von unterwegs auf den
   eigenen Server zuzugreifen; oder einen **lokalen Matrix-Server** (Docker) starten.

## 7. Wo deine Daten liegen

Alles bleibt lokal in deinem Nutzer-Ordner:
- **Windows:** `%APPDATA%\PrivacyAgent`
- **macOS:** `~/Library/Application Support/PrivacyAgent`
- **Linux:** `~/.local/share/PrivacyAgent`

Darin u.a.: `consent_log.jsonl` (Protokoll jedes Außen-Kontakts), `memories.jsonl`
(Gedächtnis), `user_settings.json` (deine Einstellungen), `mcp_servers.json`
(Skills). Du kannst diese Dateien einsehen und löschen.

**📄 Lesbares Gedächtnis (`memory.md`):** Was sich der Agent merkt, liegt zusätzlich
als **editierbare Markdown-Datei** vor – nach Person und Kategorie (Regeln/Fakten/
Vorlieben) sortiert. Im 🧠-Panel: **„Als Markdown öffnen"** zum Lesen/Bearbeiten,
**„aus Markdown neu laden"** übernimmt deine Änderungen. So siehst und steuerst du
transparent, was der Agent über dich weiß.

### 🔐 Schlüssel-Sicherheit (DSGVO Art. 32)
Deine **API-Schlüssel** (Claude, OpenRouter, Mistral …) liegen **nicht im Klartext**
in `user_settings.json`, sondern **verschlüsselt**:
- **Windows:** über **DPAPI** – an dein Windows-Konto gebunden, **nur du auf diesem
  Rechner** kannst entschlüsseln. Kein Master-Passwort, automatisch aktiv.
- **macOS/Linux:** über den **System-Schlüsselbund** (Keychain bzw. Secret Service –
  ist fest in der App enthalten).

Zusätzlich: Schlüssel werden **nie** an die KI, in Protokolle oder an fremde Skills
weitergegeben (Skills laufen mit von Geheimnissen bereinigter Umgebung), in der
Oberfläche nur als „🟢 hinterlegt" angezeigt, und beim Cloud-Aufruf nur per HTTPS
an den offiziellen Anbieter gesendet – **kein Proxy, kein Dritter**.

## 8. Häufige Fragen

**Kostet das etwas?** Die lokale KI ist kostenlos. Nur wenn du die Cloud-Eskalation
nutzt (OpenRouter/Claude), entstehen dort ggf. Kosten – und nur nach deinem OK.

**Geht etwas ohne mein Wissen ins Internet?** Nein. Außen-Kontakte laufen über eine
Einwilligung und werden protokolliert.

**Kann ich mehrere Personen zulassen?** Ja, über Matrix mit getrennten Rechten und
getrenntem Gedächtnis pro Person.

**Wie ändere ich das Modell im laufenden Betrieb?** In der Oberfläche unter Modelle
ankreuzen/auswählen; mit **Modell-Sperre** legst du es fest.

**Schickt der Agent eigenständig E-Mails?** Nur wenn du den Outlook-/Gmail-Skill mit
Schreibrechten installierst – und auch dann wird jede Schreibaktion vorher abgefragt
(außer du setzt bewusst „Vertrauen").
