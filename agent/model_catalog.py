"""Modell-Katalog -- regelmaessig aktualisierbar aus einer entfernten JSON.

Es gibt keine offizielle Ollama-API, die ALLE Bibliotheks-Modelle auflistet
(`/api/tags` liefert nur die lokal installierten). Deshalb wird der Katalog aus
einer JSON-Datei geladen (Standard: im eigenen GitHub-Repo) und lokal
zwischengespeichert. Vorteile:
  * erweiterbar OHNE Neuinstallation (einfach die JSON im Repo aendern),
  * funktioniert offline ueber den Cache bzw. die eingebaute Fallback-Liste.
"""
from __future__ import annotations

import json
import os
import time

from . import config

# Entfernte Quelle (im Repo pflegbar). Per Umgebungsvariable ueberschreibbar.
REMOTE_URL = os.environ.get(
    "CATALOG_URL",
    "https://raw.githubusercontent.com/e-man48/privacy-agent/main/catalog/models.json",
)
_CACHE_PATH = config.data_dir() / "model_catalog_cache.json"
_TTL = 24 * 3600  # einmal pro Tag aktualisieren

# Eingebaute Fallback-Liste (falls weder Cache noch Netz verfuegbar sind).
MODELS: list[dict] = [
    {"name": "qwen2.5:1.5b", "label": "Qwen 2.5 (1.5B)", "size": "~1 GB",
     "tier": "klein", "description": "Sehr klein & schnell – für schwache PCs ohne GPU."},
    {"name": "qwen2.5:3b", "label": "Qwen 2.5 (3B)", "size": "~2 GB",
     "tier": "klein", "description": "Klein, gut auf der CPU nutzbar."},
    {"name": "qwen2.5:7b", "label": "Qwen 2.5 (7B)", "size": "~4.7 GB",
     "tier": "mittel", "description": "Ausgewogen – guter Allrounder."},
    {"name": "llama3.1:8b", "label": "Llama 3.1 (8B)", "size": "~4.9 GB",
     "tier": "mittel", "description": "Metas ausgewogenes Modell."},
    {"name": "qwen2.5:14b", "label": "Qwen 2.5 (14B)", "size": "~9 GB",
     "tier": "groß", "description": "Stark – braucht viel RAM oder eine GPU."},
]


def _read_cache() -> dict | None:
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_cache(models: list[dict]) -> None:
    try:
        _CACHE_PATH.write_text(
            json.dumps({"ts": time.time(), "models": models}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


def _fetch_remote() -> list[dict] | None:
    import requests

    r = requests.get(REMOTE_URL, timeout=6)
    r.raise_for_status()
    data = r.json()
    models = data.get("models") if isinstance(data, dict) else data
    return models if isinstance(models, list) and models else None


def catalog(force: bool = False) -> list[dict]:
    """Liefert den Katalog -- frisch aus dem Netz, sonst Cache, sonst Fallback."""
    cache = _read_cache()
    if not force and cache and (time.time() - cache.get("ts", 0)) < _TTL:
        return cache["models"]
    try:
        models = _fetch_remote()
        if models:
            _write_cache(models)
            return models
    except Exception:  # noqa: BLE001 -- Netzfehler: ruhig auf Cache/Fallback gehen
        pass
    if cache and cache.get("models"):
        return cache["models"]
    return MODELS
