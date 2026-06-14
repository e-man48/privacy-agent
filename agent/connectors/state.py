"""Gemeinsamer Status der Messenger-Connectoren (fuer /status in der GUI)."""
from __future__ import annotations

STATUS: dict = {"connector": "none", "connected": False, "info": ""}


def update(connector: str, connected: bool, info: str = "") -> None:
    STATUS.update(connector=connector, connected=connected, info=info)


def snapshot() -> dict:
    return dict(STATUS)
