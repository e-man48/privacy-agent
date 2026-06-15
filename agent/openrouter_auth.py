"""OpenRouter-Anmeldung per OAuth (PKCE) -- Login im Browser, kein API-Key tippen.

Ablauf:
  1. start(): erzeugt ein PKCE-Paar, oeffnet die OpenRouter-Anmeldeseite im
     Browser (dort kann sich der Nutzer auch per Google anmelden).
  2. Nach Bestaetigung leitet OpenRouter auf unsere lokale Callback-URL zurueck
     (?code=...). exchange() tauscht den Code gegen einen API-Schluessel.

Die Callback-URL ist das ohnehin laufende lokale Backend (127.0.0.1).
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import webbrowser
from typing import Optional

from . import config

_verifier: Optional[str] = None


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def callback_url() -> str:
    return f"http://{config.HOST}:{config.PORT}/oauth/openrouter/callback"


def start() -> None:
    """Erzeugt PKCE und oeffnet die OpenRouter-Anmeldung im Browser."""
    global _verifier
    _verifier = secrets.token_urlsafe(64)
    import urllib.parse

    params = urllib.parse.urlencode({
        "callback_url": callback_url(),
        "code_challenge": _challenge(_verifier),
        "code_challenge_method": "S256",
    })
    webbrowser.open(f"https://openrouter.ai/auth?{params}")


def exchange(code: str) -> Optional[str]:
    """Tauscht den Auth-Code gegen einen OpenRouter-API-Schluessel."""
    import requests

    r = requests.post(
        "https://openrouter.ai/api/v1/auth/keys",
        json={
            "code": code,
            "code_verifier": _verifier,
            "code_challenge_method": "S256",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("key")
