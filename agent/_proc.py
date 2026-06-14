"""Hilfsfunktion, um auf Windows die aufpoppenden Konsolenfenster zu unterdruecken.

Jeder Unterprozess (ollama, npx, Installer ...) wuerde sonst kurz ein schwarzes
DOS-Fenster zeigen. Mit dem Flag CREATE_NO_WINDOW laeuft alles unsichtbar im
Hintergrund. Auf macOS/Linux gibt es das Problem nicht.
"""
from __future__ import annotations

import os

CREATE_NO_WINDOW = 0x08000000


def no_window() -> dict:
    """Zusatz-Argumente fuer subprocess, damit kein Fenster aufpoppt."""
    return {"creationflags": CREATE_NO_WINDOW} if os.name == "nt" else {}
