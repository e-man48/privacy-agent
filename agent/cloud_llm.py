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


def is_configured() -> bool:
    return bool(config.ANTHROPIC_API_KEY)


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
    """Sendet eine Anfrage an Claude. Setzt einen gueltigen API-Key voraus."""
    if not is_configured():
        raise CloudLLMError(
            "Kein Anthropic-API-Schluessel hinterlegt. Cloud-Notfall nicht moeglich."
        )
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
