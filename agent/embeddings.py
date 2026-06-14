"""Lokale Text-Embeddings ueber Ollama -- fuer das semantische Gedaechtnis.

Wandelt Text in Vektoren um, sodass Aehnlichkeit ueber Bedeutung (nicht nur
Wortgleichheit) bestimmt werden kann. Laeuft komplett lokal (DSGVO-konform).

Ist das Embedding-Modell nicht vorhanden, liefern die Funktionen None bzw.
False -- die Aufrufer fallen dann automatisch auf die lexikalische Suche zurueck.
"""
from __future__ import annotations

import math
from typing import Optional

import requests

from . import config

# Kurzer Cache des Verfuegbarkeits-Checks, um nicht bei jedem Aufruf zu fragen.
_available: Optional[bool] = None


def is_available(refresh: bool = False) -> bool:
    """Prueft, ob das Embedding-Modell lokal geladen ist."""
    global _available
    if _available is not None and not refresh:
        return _available
    try:
        r = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=2)
        r.raise_for_status()
        names = {m["name"] for m in r.json().get("models", [])}
        base = config.EMBED_MODEL.split(":")[0]
        _available = any(n.split(":")[0] == base for n in names)
    except requests.RequestException:
        _available = False
    return _available


def embed(text: str) -> Optional[list[float]]:
    """Liefert den Embedding-Vektor eines Textes -- oder None bei Fehler."""
    if not text.strip():
        return None
    try:
        r = requests.post(
            f"{config.OLLAMA_HOST}/api/embeddings",
            json={"model": config.EMBED_MODEL, "prompt": text},
            timeout=30,
        )
        r.raise_for_status()
        vec = r.json().get("embedding")
        return vec if vec else None
    except requests.RequestException:
        return None


def cosine(a: Optional[list[float]], b: Optional[list[float]]) -> float:
    """Kosinus-Aehnlichkeit zweier Vektoren (0..1 fuer aehnliche Texte)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
