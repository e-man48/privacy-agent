"""Vom GUI-Einrichtungs-Assistenten gespeicherte Nutzereinstellungen.

Damit kann ein Laie den Agenten komplett ueber die Oberflaeche konfigurieren --
ohne je eine .env-Datei anzufassen. Gespeichert als JSON im Nutzer-Datenordner;
beim Backend-Start liest config diese Werte ein (siehe config.apply_user_settings).
"""
from __future__ import annotations

import json

from . import config

# Schluessel, die der Assistent setzen darf (Whitelist).
_ALLOWED = {
    "onboarded",
    "anthropic_api_key", "cloud_model", "local_model",
    "local_backend", "local_openai_base_url", "local_openai_model",
    "local_openai_api_key",
    "decision_style", "auto_local_upgrade", "auto_download_models",
    "model_locked", "cloud_mode", "browser_provider",
    "cloud_provider", "openrouter_api_key", "openrouter_model",
    "mistral_api_key", "mistral_model",
    "connector",
    "matrix_homeserver", "matrix_user", "matrix_password",
    "matrix_access_token", "matrix_allowed_users", "matrix_admin_users",
}

# Schluessel, die in /setup/state NICHT im Klartext zurueckgegeben werden.
_SECRET = {"anthropic_api_key", "matrix_password", "matrix_access_token",
           "openrouter_api_key", "local_openai_api_key", "mistral_api_key"}


def load() -> dict:
    try:
        return json.loads(config.USER_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save(partial: dict) -> dict:
    """Fuegt Einstellungen zusammen, speichert sie und macht sie sofort aktiv."""
    data = load()
    for key, value in partial.items():
        if key in _ALLOWED:
            data[key] = value
    config.USER_SETTINGS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    config.apply_user_settings(data)  # sofort wirksam, kein Neustart noetig
    return data


def public() -> dict:
    """Einstellungen fuer die GUI -- Geheimnisse nur als 'gesetzt: ja/nein'."""
    data = load()
    out = {}
    for key, value in data.items():
        if key in _SECRET:
            out[key + "_set"] = bool(value)
        else:
            out[key] = value
    return out
