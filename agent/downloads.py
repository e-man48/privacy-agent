"""Gemeinsame Verwaltung laufender Modell-Downloads (Ollama).

Sowohl der Autopilot (autonom) als auch manuelle Downloads aus dem Katalog
nutzen dies -- so kennt die Oberflaeche jederzeit, was gerade geladen wird.
"""
from __future__ import annotations

import subprocess
import threading

from . import metrics
from ._proc import no_window

_active: set[str] = set()


def active() -> list[str]:
    return sorted(_active)


def is_downloading(model: str) -> bool:
    return model in _active


def pull(model: str) -> None:
    """Laedt ein Modell im Hintergrund (doppelte Starts werden ignoriert)."""
    if model in _active:
        return
    _active.add(model)

    def worker() -> None:
        try:
            subprocess.run(["ollama", "pull", model], check=True, **no_window())
            metrics.record("model_download", model=model)
        except Exception:  # noqa: BLE001
            pass
        finally:
            _active.discard(model)

    threading.Thread(target=worker, daemon=True).start()
