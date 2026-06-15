"""Zentrale Konfiguration des Agenten.

Werte koennen ueber Umgebungsvariablen ueberschrieben werden, damit die
Tauri-Huelle bzw. der Einrichtungs-Assistent sie zur Laufzeit setzen kann.
"""
from __future__ import annotations

import os
from pathlib import Path


# --- Lokale KI (Ollama) -------------------------------------------------
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
# Wird vom Einrichtungs-Assistenten anhand der Hardware gesetzt.
LOCAL_MODEL = os.environ.get("LOCAL_MODEL", "qwen2.5:7b")
# Lokales Embedding-Modell fuer das semantische Gedaechtnis (klein, ~270 MB).
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")

# --- Cloud-Notfall (Anthropic / Claude) ---------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
# Standard: guenstiges, schnelles Modell fuer den Notfall.
CLOUD_MODEL = os.environ.get("CLOUD_MODEL", "claude-haiku-4-5-20251001")
# Fuer schwierige Faelle kann auf das staerkste Modell hochgestuft werden.
CLOUD_MODEL_STRONG = os.environ.get("CLOUD_MODEL_STRONG", "claude-opus-4-8")

# --- Notfall-Modus ------------------------------------------------------
# "off"     : nie Cloud, bleibt rein lokal.
# "api"     : Cloud per API (nach Einwilligung) -- bisheriges Verhalten.
# "browser" : Abo-Hilfe -- oeffnet das Web-Chat des Abos im Browser (nur am PC),
#             der Mensch nutzt sein eigenes Abo. Frage kommt in die Zwischenablage.
CLOUD_MODE = os.environ.get("CLOUD_MODE", "api")
# Welches Abo-Web-Chat im Browser-Modus geoeffnet wird: claude | chatgpt | gemini.
BROWSER_PROVIDER = os.environ.get("BROWSER_PROVIDER", "claude")

# Im API-Modus: welcher Anbieter? "anthropic" (Claude) | "openrouter" (viele Modelle).
CLOUD_PROVIDER = os.environ.get("CLOUD_PROVIDER", "anthropic")
# OpenRouter: ein Konto/Login -> Zugang zu Claude, GPT, Gemini u.v.m.
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
# "openrouter/auto" waehlt automatisch ein passendes Modell (sicherer Standard).
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/auto")

# --- Eskalations-Schwellen ----------------------------------------------
# Selbstbewertung 0-10; darunter wird eine Cloud-Eskalation vorgeschlagen.
CONFIDENCE_THRESHOLD = int(os.environ.get("CONFIDENCE_THRESHOLD", "6"))
# Maximale lokale Wiederholungsversuche, bevor eskaliert wird.
MAX_LOCAL_RETRIES = int(os.environ.get("MAX_LOCAL_RETRIES", "1"))


def _as_bool(v) -> bool:
    return v if isinstance(v, bool) else str(v).strip().lower() in (
        "1", "true", "yes", "on", "ja")


# Autopilot: Bei Schwierigkeiten autonom auf ein staerkeres LOKALES Modell
# wechseln, bevor die Cloud vorgeschlagen wird (kostenlos, lokal, reversibel).
AUTO_LOCAL_UPGRADE = _as_bool(os.environ.get("AUTO_LOCAL_UPGRADE", "true"))

# Modell-Sperre: Wenn aktiv, darf der Agent (Autopilot/Optimierer) das Modell
# NICHT mehr aendern -- nur der Mensch stellt es um, und es bleibt so.
MODEL_LOCKED = _as_bool(os.environ.get("MODEL_LOCKED", "false"))

# --- Semantisches Gedaechtnis (Embeddings) ------------------------------
# Kosinus-Aehnlichkeit, ab der zwei Eintraege als Duplikat/Synonym gelten.
SEMANTIC_DUP_THRESHOLD = float(os.environ.get("SEMANTIC_DUP_THRESHOLD", "0.82"))
# Mindest-Aehnlichkeit, damit ein Eintrag bei der Suche als relevant gilt.
SEMANTIC_MIN_SIM = float(os.environ.get("SEMANTIC_MIN_SIM", "0.45"))

# --- Code-Sandbox (Werkzeug run_python) ---------------------------------
# "auto" nutzt Docker, falls verfuegbar, sonst den eingeschraenkten Subprozess.
SANDBOX_BACKEND = os.environ.get("SANDBOX_BACKEND", "auto")  # auto | docker | subprocess
SANDBOX_IMAGE = os.environ.get("SANDBOX_IMAGE", "python:3.12-slim")
SANDBOX_TIMEOUT = int(os.environ.get("SANDBOX_TIMEOUT", "10"))  # Sekunden
SANDBOX_MEM_MB = int(os.environ.get("SANDBOX_MEM_MB", "256"))   # Speicherlimit


# --- Messenger-Connector (z.B. Matrix) ----------------------------------
# Welcher Messenger den Agenten erreichbar macht: "none" | "matrix".
CONNECTOR = os.environ.get("CONNECTOR", "none")

# Matrix (privater/eigener Homeserver empfohlen, DSGVO-konform).
MATRIX_HOMESERVER = os.environ.get("MATRIX_HOMESERVER", "")
MATRIX_USER = os.environ.get("MATRIX_USER", "")            # @agent:dein-server.de
MATRIX_PASSWORD = os.environ.get("MATRIX_PASSWORD", "")
MATRIX_ACCESS_TOKEN = os.environ.get("MATRIX_ACCESS_TOKEN", "")  # statt Passwort
MATRIX_DEVICE_NAME = os.environ.get("MATRIX_DEVICE_NAME", "PrivacyAgent")
# Nur diese Nutzer duerfen den Agenten steuern (kommagetrennt). LEER = niemand!
MATRIX_ALLOWED_USERS = os.environ.get("MATRIX_ALLOWED_USERS", "")
# Diese Nutzer duerfen die (bezahlte) Cloud freigeben (kommagetrennt).
# LEER = alle erlaubten Nutzer duerfen es (abwaertskompatibel).
MATRIX_ADMIN_USERS = os.environ.get("MATRIX_ADMIN_USERS", "")


def matrix_allowed_users() -> set[str]:
    return {u.strip() for u in MATRIX_ALLOWED_USERS.split(",") if u.strip()}


def matrix_admin_users() -> set[str]:
    return {u.strip() for u in MATRIX_ADMIN_USERS.split(",") if u.strip()}


def matrix_store_dir():
    d = data_dir() / "matrix"
    d.mkdir(parents=True, exist_ok=True)
    return d


# --- Server -------------------------------------------------------------
HOST = os.environ.get("AGENT_HOST", "127.0.0.1")
PORT = int(os.environ.get("AGENT_PORT", "8765"))

# --- Datenablage (DSGVO-Protokoll, Einstellungen) -----------------------
def data_dir() -> Path:
    """Plattformuebergreifender, nutzerspezifischer Datenordner."""
    if os.name == "nt":  # Windows
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif os.sys.platform == "darwin":  # macOS
        base = Path.home() / "Library" / "Application Support"
    else:  # Linux
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / "PrivacyAgent"
    d.mkdir(parents=True, exist_ok=True)
    return d


CONSENT_LOG_PATH = data_dir() / "consent_log.jsonl"
MEMORY_PATH = data_dir() / "memories.jsonl"
METRICS_PATH = data_dir() / "metrics.jsonl"
OVERRIDES_PATH = data_dir() / "overrides.json"
OPTIMIZATION_LOG_PATH = data_dir() / "optimization_log.jsonl"
AUTOPILOT_PATH = data_dir() / "autopilot.json"  # Erfahrungs-Speicher pro Modell
USER_SETTINGS_PATH = data_dir() / "user_settings.json"  # vom GUI-Assistenten
MCP_CONFIG_PATH = data_dir() / "mcp_servers.json"        # externe Skills (MCP)


def load_mcp_servers() -> list[dict]:
    """Liest die MCP-Server-Konfiguration.

    Unterstuetzt das verbreitete `mcpServers`-Format (wie Claude Desktop) sowie
    eine einfache Liste. Jeder Eintrag: name, command, args, env, trust, enabled.
    """
    import json

    try:
        data = json.loads(MCP_CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    if isinstance(data, dict) and "mcpServers" in data:
        return [{"name": k, **v} for k, v in data["mcpServers"].items()]
    if isinstance(data, dict) and "servers" in data:
        return data["servers"]
    return data if isinstance(data, list) else []


def save_mcp_servers(servers: list[dict]) -> None:
    import json

    MCP_CONFIG_PATH.write_text(
        json.dumps({"servers": servers}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# --- Selbstoptimierung: Whitelist aenderbarer Parameter ------------------
# Der Optimierer darf AUSSCHLIESSLICH diese Werte aendern -- jeweils nur ueber
# set_override(), nur nach Nutzer-Genehmigung. Kein Zugriff auf Quellcode.
_TUNABLE: dict[str, object] = {
    "CONFIDENCE_THRESHOLD": int,
    "MAX_LOCAL_RETRIES": int,
    "LOCAL_MODEL": str,
    "CLOUD_MODEL": str,
    "AUTO_LOCAL_UPGRADE": _as_bool,
}


def _load_overrides() -> dict:
    import json

    try:
        return json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def set_override(key: str, value) -> object:
    """Setzt einen erlaubten Parameter dauerhaft und sofort wirksam.

    Gibt den vorherigen Wert zurueck (fuer Protokoll/Rueckgaengig-Machen).
    """
    import json

    if key not in _TUNABLE:
        raise ValueError(f"Parameter '{key}' ist nicht aenderbar.")
    value = _TUNABLE[key](value)
    previous = globals().get(key)
    data = _load_overrides()
    data[key] = value
    OVERRIDES_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    globals()[key] = value  # im laufenden Prozess sofort aktiv
    return previous


def _apply_overrides() -> None:
    for key, value in _load_overrides().items():
        if key in _TUNABLE:
            globals()[key] = _TUNABLE[key](value)


# --- Vom GUI-Einrichtungs-Assistenten gesetzte Einstellungen -------------
# Diese erlauben es Laien, ALLES ohne .env zu konfigurieren. Reihenfolge der
# Geltung: env-Standard -> user_settings.json -> overrides.json (Optimierer).
_DECISION_STYLE = {"cautious": 8, "balanced": 6, "autonomous": 4}


def apply_user_settings(data: dict) -> None:
    """Uebernimmt die im GUI gespeicherten Einstellungen in die Konfiguration."""
    g = globals()
    if data.get("anthropic_api_key") is not None:
        g["ANTHROPIC_API_KEY"] = str(data["anthropic_api_key"])
    if data.get("cloud_model"):
        g["CLOUD_MODEL"] = str(data["cloud_model"])
    if data.get("local_model"):
        g["LOCAL_MODEL"] = str(data["local_model"])
    if "auto_local_upgrade" in data:
        g["AUTO_LOCAL_UPGRADE"] = _as_bool(data["auto_local_upgrade"])
    if "model_locked" in data:
        g["MODEL_LOCKED"] = _as_bool(data["model_locked"])
    if data.get("cloud_mode") in ("off", "api", "browser"):
        g["CLOUD_MODE"] = data["cloud_mode"]
    if data.get("browser_provider") in ("claude", "chatgpt", "gemini"):
        g["BROWSER_PROVIDER"] = data["browser_provider"]
    if data.get("cloud_provider") in ("anthropic", "openrouter"):
        g["CLOUD_PROVIDER"] = data["cloud_provider"]
    if data.get("openrouter_api_key") is not None:
        g["OPENROUTER_API_KEY"] = str(data["openrouter_api_key"])
    if data.get("openrouter_model"):
        g["OPENROUTER_MODEL"] = str(data["openrouter_model"])
    if data.get("decision_style") in _DECISION_STYLE:
        g["CONFIDENCE_THRESHOLD"] = _DECISION_STYLE[data["decision_style"]]
    if "connector" in data:
        g["CONNECTOR"] = str(data["connector"] or "none")
    for src, dst in (
        ("matrix_homeserver", "MATRIX_HOMESERVER"),
        ("matrix_user", "MATRIX_USER"),
        ("matrix_password", "MATRIX_PASSWORD"),
        ("matrix_access_token", "MATRIX_ACCESS_TOKEN"),
        ("matrix_allowed_users", "MATRIX_ALLOWED_USERS"),
        ("matrix_admin_users", "MATRIX_ADMIN_USERS"),
    ):
        if src in data:
            g[dst] = str(data[src] or "")


def _load_user_settings() -> dict:
    import json

    try:
        return json.loads(USER_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


apply_user_settings(_load_user_settings())
_apply_overrides()
