"""Cloud-Notfall ueber die Anthropic-/Claude-API.

WICHTIG: Diese Funktion wird ausschliesslich nach ausdruecklicher Einwilligung
des Nutzers aufgerufen (siehe router.py / consent_log.py). Jeder Aufruf wird
protokolliert, damit nachvollziehbar bleibt, welche Daten das Geraet verlassen.
"""
from __future__ import annotations

from typing import Optional

from . import config


class CloudLLMError(RuntimeError):
    """Cloud-KI nicht erreichbar oder nicht konfiguriert."""


def _providers() -> list[str]:
    """Reihenfolge der Cloud-Anbieter fuer die Notfall-Eskalation.

    Lokale KI laeuft immer zuerst (siehe router.py). Reicht sie nicht, wird in
    dieser Reihenfolge eskaliert -- jeweils nur, wenn ein Schluessel vorliegt:

    * CLOUD_PROVIDER == "openrouter" (Standard): erst OpenRouter, dann Claude.
    * CLOUD_PROVIDER == "anthropic": ausschliesslich Claude (Anthropic).
    """
    avail: list[str] = []
    if config.CLOUD_PROVIDER == "openrouter":
        if config.OPENROUTER_API_KEY:
            avail.append("openrouter")
        if config.ANTHROPIC_API_KEY:
            avail.append("anthropic")
    else:  # "anthropic" -> nur Claude direkt
        if config.ANTHROPIC_API_KEY:
            avail.append("anthropic")
    return avail


def is_configured() -> bool:
    return bool(_providers())


def test_key(api_key: str) -> tuple[bool, str]:
    """Prueft einen Anthropic-Schluessel mit einem winzigen Test-Aufruf."""
    if not api_key.strip():
        return False, "Kein Schluessel eingegeben."
    try:
        import anthropic
    except ImportError:
        return False, "Paket 'anthropic' nicht installiert."
    try:
        client = anthropic.Anthropic(api_key=api_key.strip())
        client.messages.create(
            model=config.CLOUD_MODEL,
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        return True, "Schluessel funktioniert."
    except Exception as exc:  # ungueltiger Schluessel, Netzfehler, ...
        return False, f"Schluessel abgelehnt oder nicht erreichbar: {exc}"


def chat(messages: list[dict], system: Optional[str] = None, strong: bool = False) -> str:
    """Eskaliert in fester Reihenfolge: erst OpenRouter, dann Claude.

    Schlaegt ein Anbieter fehl (Netz/Auth), wird automatisch der naechste in der
    Kette versucht. Erst wenn alle scheitern, wird der Fehler weitergereicht.
    """
    providers = _providers()
    if not providers:
        raise CloudLLMError("Kein Cloud-Zugang hinterlegt. Notfall-Hilfe nicht moeglich.")
    last_err: Optional[CloudLLMError] = None
    for prov in providers:
        try:
            if prov == "openrouter":
                return _chat_openrouter(messages, system)
            return _chat_anthropic(messages, system, strong)
        except CloudLLMError as exc:
            last_err = exc  # naechsten Anbieter in der Kette versuchen
    raise last_err  # type: ignore[misc]


def _chat_openrouter(messages: list[dict], system: Optional[str]) -> str:
    """OpenRouter (OpenAI-kompatibel) -- ein Zugang zu vielen Modellen."""
    import requests

    msgs = ([{"role": "system", "content": system}] if system else []) + messages
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://privacy-agent.local",
                "X-Title": "Privacy-Agent",
            },
            json={"model": config.OPENROUTER_MODEL, "messages": msgs, "max_tokens": 2048},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:  # Netz-/Auth-/Format-Fehler
        raise CloudLLMError(f"OpenRouter-Aufruf fehlgeschlagen: {exc}") from exc


def _chat_anthropic(messages: list[dict], system: Optional[str], strong: bool) -> str:
    try:
        import anthropic  # lokal importiert, damit der lokale Pfad ohne SDK laeuft
    except ImportError as exc:
        raise CloudLLMError("Paket 'anthropic' nicht installiert.") from exc

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    model = config.CLOUD_MODEL_STRONG if strong else config.CLOUD_MODEL
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system or "Du bist ein praeziser, hilfreicher Assistent.",
            messages=messages,
        )
    except Exception as exc:  # anthropic.APIError u.a.
        raise CloudLLMError(f"Cloud-Aufruf fehlgeschlagen: {exc}") from exc

    return "".join(block.text for block in resp.content if block.type == "text").strip()
