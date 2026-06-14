"""Messenger-Connectoren -- machen den Agenten ueber einen Messenger erreichbar.

Pluggbar: aktuell ist Matrix als Referenz implementiert; weitere (Signal,
Telegram, ...) lassen sich nach demselben Muster ergaenzen. WhatsApp wird am
sinnvollsten ueber eine Matrix-Bridge angebunden (siehe README).

Der aktive Connector laeuft als asyncio-Task im selben Prozess wie das Backend
und wird beim Start automatisch hochgefahren, wenn CONNECTOR konfiguriert ist.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from .. import config
from . import state

_task: Optional[asyncio.Task] = None


async def maybe_start() -> None:
    """Startet den konfigurierten Connector (falls vorhanden)."""
    global _task
    if config.CONNECTOR != "matrix":
        return
    try:
        from .matrix_connector import MatrixConnector
    except ImportError as exc:
        state.update("matrix", False, f"Paket 'matrix-nio' fehlt: {exc}")
        return
    connector = MatrixConnector()
    _task = asyncio.create_task(connector.run())
    state.update("matrix", False, "Starte ...")


async def restart() -> None:
    """Connector neu starten (z.B. nachdem die GUI die Einstellungen aenderte)."""
    await shutdown()
    await maybe_start()


async def shutdown() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None


def status() -> dict:
    return state.snapshot()
