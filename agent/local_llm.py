"""Anbindung an die lokale KI ueber Ollama.

Alles hier laeuft ausschliesslich auf dem Geraet des Nutzers -- es verlaesst
keine Information das System. Damit ist dieser Pfad von Natur aus DSGVO-konform.
"""
from __future__ import annotations

import json
import re
from typing import Optional

import requests

from . import config


class LocalLLMError(RuntimeError):
    """Lokale KI nicht erreichbar oder Antwort fehlerhaft."""


def is_available() -> bool:
    """Prueft, ob der Ollama-Dienst laeuft."""
    try:
        r = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=2)
        return r.status_code == 200
    except requests.RequestException:
        return False


def list_models() -> list[str]:
    """Liefert die Namen aller lokal installierten Ollama-Modelle."""
    try:
        r = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except requests.RequestException:
        return []


def has_model(model: str) -> bool:
    """Prueft, ob das gewuenschte Modell bereits lokal vorhanden ist."""
    try:
        r = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=5)
        r.raise_for_status()
        names = {m["name"] for m in r.json().get("models", [])}
        # Ollama listet z.B. "qwen2.5:7b"; akzeptiere auch ohne :tag.
        return model in names or any(n.split(":")[0] == model.split(":")[0] for n in names)
    except requests.RequestException:
        return False


def chat(messages: list[dict], model: Optional[str] = None, temperature: float = 0.3) -> str:
    """Fuehrt einen Chat-Aufruf gegen die lokale KI aus.

    Nutzt **Streaming**: Ollama liefert die Antwort Token fuer Token, statt sie
    erst komplett zu berechnen und am Stueck zu senden. Dadurch trifft das
    Lese-Zeitlimit nicht mehr waehrend einer noch laufenden, langsamen Antwort
    (haeufige Ursache fuer "Read timed out"). `keep_alive` haelt das Modell
    danach im Speicher, damit nicht jede Anfrage einen Kaltstart ausloest.
    """
    model = model or config.LOCAL_MODEL
    try:
        with requests.post(
            f"{config.OLLAMA_HOST}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": True,
                "keep_alive": config.OLLAMA_KEEP_ALIVE,
                "options": {"temperature": temperature},
            },
            stream=True,
            # (Verbindungs-Timeout, Lese-Timeout je Datenpaket). Das Lese-Timeout
            # wird mit jedem Token zurueckgesetzt -- es greift nur, wenn Ollama
            # gar nichts liefert (z.B. beim erstmaligen Laden eines grossen Modells).
            timeout=(10, config.LOCAL_READ_TIMEOUT),
        ) as r:
            r.raise_for_status()
            parts: list[str] = []
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                obj = json.loads(line)
                if obj.get("error"):
                    raise LocalLLMError(f"Ollama meldet: {obj['error']}")
                chunk = (obj.get("message") or {}).get("content")
                if chunk:
                    parts.append(chunk)
                if obj.get("done"):
                    break
            return "".join(parts).strip()
    except requests.RequestException as exc:
        raise LocalLLMError(f"Lokale KI nicht erreichbar: {exc}") from exc
    except (KeyError, json.JSONDecodeError) as exc:
        raise LocalLLMError(f"Unerwartete Antwort der lokalen KI: {exc}") from exc


def self_rate(question: str, answer: str) -> int:
    """Laesst das lokale Modell seine eigene Antwort von 0-10 bewerten.

    Liefert eine grobe Konfidenz, die der Router fuer die Eskalations-
    Entscheidung nutzt. Bei Unklarheit wird konservativ 0 zurueckgegeben.
    """
    rating_prompt = [
        {
            "role": "system",
            "content": (
                "Du bewertest, wie sicher und korrekt eine gegebene Antwort die "
                "Frage des Nutzers loest. Antworte mit GENAU einer ganzen Zahl "
                "von 0 (voellig unsicher/falsch) bis 10 (voellig sicher/korrekt). "
                "Keine weiteren Worte."
            ),
        },
        {
            "role": "user",
            "content": f"FRAGE:\n{question}\n\nANTWORT:\n{answer}\n\nBewertung (0-10):",
        },
    ]
    try:
        raw = chat(rating_prompt, temperature=0.0)
    except LocalLLMError:
        return 0
    match = re.search(r"\b(10|\d)\b", raw)
    return int(match.group(1)) if match else 0
