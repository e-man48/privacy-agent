"""Matrix-Connector -- macht den Agenten ueber einen Matrix-Raum erreichbar.

Empfohlen mit eigenem/privatem Homeserver (z.B. Synapse/Conduit), damit die
Kommunikation den eigenen Bereich nicht verlaesst. Ende-zu-Ende-Verschluesselung
wird automatisch genutzt, wenn 'python-olm' installiert ist.

Sicherheit:
  * Nur Nutzer aus MATRIX_ALLOWED_USERS duerfen den Agenten steuern.
  * Nachrichten von vor dem Start werden ignoriert (keine Alt-Last).
  * Eine LEERE Allowlist bedeutet: niemand darf -> der Connector warnt und
    antwortet niemandem (sicherer Standard).
"""
from __future__ import annotations

import asyncio
import time

from .. import config, principals
from . import state
from .session import Conversations

try:  # E2EE nur, wenn libolm/python-olm vorhanden ist
    import olm  # noqa: F401
    _E2EE = True
except ImportError:
    _E2EE = False


async def test_connection(homeserver: str, user: str,
                          password: str = "", token: str = "") -> tuple[bool, str]:
    """Prueft die Matrix-Zugangsdaten mit einem echten Anmeldeversuch.

    Wird vom Einrichtungs-Assistenten genutzt, damit ein Laie sofort sieht, ob
    die Verbindung klappt -- ohne Logs lesen zu muessen.
    """
    if not homeserver.strip() or not user.strip():
        return False, "Bitte Server-Adresse und Agenten-Konto angeben."
    try:
        from nio import AsyncClient, LoginResponse, WhoamiResponse
    except ImportError:
        return False, "Paket 'matrix-nio' ist nicht installiert."

    client = AsyncClient(homeserver.strip(), user.strip())
    try:
        if token.strip():
            client.access_token = token.strip()
            client.user_id = user.strip()
            resp = await client.whoami()
            if isinstance(resp, WhoamiResponse):
                return True, f"Verbunden als {resp.user_id}."
            return False, f"Zugangstoken abgelehnt: {resp}"
        resp = await client.login(password, device_name="PrivacyAgent-Test")
        if isinstance(resp, LoginResponse):
            return True, "Anmeldung erfolgreich – die Verbindung funktioniert."
        return False, f"Anmeldung fehlgeschlagen: {getattr(resp, 'message', resp)}"
    except Exception as exc:  # falscher Server, kein Netz, ...
        return False, f"Verbindung fehlgeschlagen: {exc}"
    finally:
        await client.close()


class MatrixConnector:
    def __init__(self) -> None:
        self._convo = Conversations()
        self._start_ms = int(time.time() * 1000)
        self._client = None

    async def run(self) -> None:
        from nio import AsyncClient, AsyncClientConfig, LoginResponse, RoomMessageText

        allowed = config.matrix_allowed_users()
        if not allowed:
            state.update("matrix", False,
                         "Keine MATRIX_ALLOWED_USERS gesetzt -- Connector inaktiv.")
            return

        client_config = AsyncClientConfig(
            store_sync_tokens=True, encryption_enabled=_E2EE
        )
        client = AsyncClient(
            config.MATRIX_HOMESERVER,
            config.MATRIX_USER,
            store_path=str(config.matrix_store_dir()),
            config=client_config,
        )
        self._client = client

        # Anmeldung: Access-Token bevorzugt, sonst Passwort.
        try:
            if config.MATRIX_ACCESS_TOKEN:
                client.access_token = config.MATRIX_ACCESS_TOKEN
                client.user_id = config.MATRIX_USER
                whoami = await client.whoami()
                client.device_id = getattr(whoami, "device_id", None)
            else:
                resp = await client.login(
                    config.MATRIX_PASSWORD, device_name=config.MATRIX_DEVICE_NAME
                )
                if not isinstance(resp, LoginResponse):
                    state.update("matrix", False, f"Anmeldung fehlgeschlagen: {resp}")
                    return
            if _E2EE:
                client.load_store()
        except Exception as exc:  # Netzwerk-/Auth-Fehler -> nicht die App killen
            state.update("matrix", False, f"Verbindung fehlgeschlagen: {exc}")
            return

        async def on_message(room, event) -> None:
            # Eigene und alte Nachrichten ignorieren.
            if event.sender == client.user_id:
                return
            if event.server_timestamp < self._start_ms:
                return
            if event.sender not in allowed:
                return  # nicht autorisiert -> stillschweigend ignorieren

            text = (event.body or "").strip()
            if not text:
                return

            # Pro-Person-Identitaet (eigenes Gedaechtnis + eigene Rechte).
            principal = principals.for_matrix(event.sender)
            # Brain-Logik blockiert (requests) -> in Thread auslagern.
            loop = asyncio.get_running_loop()
            reply = await loop.run_in_executor(
                None, self._convo.process, principal, text
            )
            await client.room_send(
                room.room_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": reply},
            )

        client.add_event_callback(on_message, RoomMessageText)
        state.update("matrix", True, f"Verbunden als {config.MATRIX_USER} "
                                     f"(E2EE: {'an' if _E2EE else 'aus'}).")
        try:
            await client.sync_forever(timeout=30000, full_state=True)
        except asyncio.CancelledError:
            pass
        finally:
            await client.close()
            state.update("matrix", False, "Getrennt.")
