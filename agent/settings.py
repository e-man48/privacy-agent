"""Vom GUI-Einrichtungs-Assistenten gespeicherte Nutzereinstellungen.

Damit kann ein Laie den Agenten komplett ueber die Oberflaeche konfigurieren --
ohne je eine .env-Datei anzufassen. Gespeichert als JSON im Nutzer-Datenordner;
beim Backend-Start liest config diese Werte ein (siehe config.apply_user_settings).
"""
from __future__ import annotations

import json

from . import config, secret_store

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
    """Liest die Einstellungen und entschluesselt die Geheimnisse (in den Speicher)."""
    try:
        data = json.loads(config.USER_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return secret_store.reveal(data)


def _write(data: dict) -> None:
    """Schreibt die Einstellungen -- Geheimnisse dabei VERSCHLUESSELT (nie Klartext)."""
    to_store = dict(data)
    for key in _SECRET:
        value = to_store.get(key)
        if value:
            to_store[key] = secret_store.encrypt(key, str(value))
    config.USER_SETTINGS_PATH.write_text(
        json.dumps(to_store, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def save(partial: dict) -> dict:
    """Fuegt Einstellungen zusammen, speichert sie (verschluesselt) und macht sie aktiv."""
    data = load()
    for key, value in partial.items():
        if key in _ALLOWED:
            data[key] = value
    _write(data)
    config.apply_user_settings(data)  # sofort wirksam (Klartext im Speicher)
    return data


def migrate_secrets() -> None:
    """Verschluesselt einmalig evtl. noch im Klartext gespeicherte Geheimnisse.

    Wird beim Backend-Start aufgerufen. Liegt schon alles verschluesselt vor oder
    gibt es kein Krypto-Backend (selten), passiert nichts.
    """
    if secret_store.backend() == "plain":
        return
    try:
        raw = json.loads(config.USER_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return
    needs = any(raw.get(k) and not secret_store.is_encrypted(raw[k]) for k in _SECRET)
    if needs:
        _write(secret_store.reveal(raw))  # neu schreiben -> Geheimnisse verschluesselt


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
