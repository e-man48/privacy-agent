"""Ollama im laufenden Betrieb bereitstellen: installieren und (im Notfall) aktualisieren.

Bisher installierte nur der Ersteinrichtungs-Assistent Ollama. Dieses Modul macht
dasselbe waehrend des Betriebs -- damit die App auch dann funktioniert, wenn Ollama
fehlt oder zu alt ist (z.B. ohne Function-Calling/`tools`). Alles best effort und
im Hintergrund; der Status ist ueber status() abrufbar (GUI zeigt ihn an).
"""
from __future__ import annotations

import os
import platform
import subprocess
import threading
from typing import Optional

from . import config
from ._proc import no_window

# Ab dieser Ollama-Version gibt es Function-Calling (tools). Darunter -> veraltet.
_MIN_TOOLS_VERSION = (0, 3, 0)

_STATE = {"busy": False, "action": "", "message": ""}
_lock = threading.Lock()


def status() -> dict:
    return dict(_STATE)


def find() -> Optional[str]:
    from . import local_llm  # nutzt dieselbe Suche wie der Start
    return local_llm._find_ollama()


def installed() -> bool:
    return find() is not None


def version() -> Optional[tuple]:
    import requests
    try:
        raw = requests.get(f"{config.OLLAMA_HOST}/api/version", timeout=3).json().get("version", "")
        parts = tuple(int(x) for x in raw.split(".")[:3] if x.isdigit())
        return parts or None
    except Exception:  # noqa: BLE001
        return None


def is_outdated() -> bool:
    v = version()
    return v is not None and v < _MIN_TOOLS_VERSION


def _emit(msg: str) -> None:
    _STATE["message"] = msg


def _download(url: str, dest: str) -> None:
    import requests
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 16):
                fh.write(chunk)


def _run_installer() -> bool:
    """Installiert ODER aktualisiert Ollama (Re-Installer aktualisiert in-place)."""
    system = platform.system()
    try:
        if system == "Darwin":
            # 'brew install' installiert bzw. aktualisiert (mit reinstall-Fallback).
            subprocess.run(["brew", "install", "ollama"], check=False)
            subprocess.run(["brew", "upgrade", "ollama"], check=False)
        elif system == "Linux":
            import requests
            script = requests.get("https://ollama.com/install.sh", timeout=60).text
            subprocess.run(["sh", "-c", script], check=True)
        elif system == "Windows":
            tmp = os.path.join(os.environ.get("TEMP", "."), "OllamaSetup.exe")
            _emit("Lade Ollama herunter …")
            _download("https://ollama.com/download/OllamaSetup.exe", tmp)
            _emit("Installiere/aktualisiere Ollama (still) …")
            subprocess.run([tmp, "/VERYSILENT", "/NORESTART"], check=True, **no_window())
        else:
            return False
    except Exception as exc:  # noqa: BLE001  -- Netz-/Installer-Fehler melden
        _emit(f"Fehlgeschlagen: {exc}")
        return False
    return True


def provision(install_if_missing: bool = True, update_if_old: bool = True) -> bool:
    """Stellt Ollama bereit: installiert (falls fehlt) bzw. aktualisiert (falls alt).

    Danach wird der Dienst gestartet. Laeuft synchron -- aus einem Hintergrund-
    Thread aufrufen (provision_async). Nie eine Ausnahme nach aussen.
    """
    if not _lock.acquire(blocking=False):
        return False
    _STATE.update(busy=True, action="", message="")
    try:
        if not installed():
            if not (install_if_missing and config.AUTO_INSTALL_OLLAMA):
                return False
            _STATE["action"] = "install"
            _emit("Ollama wird installiert …")
            if not _run_installer():
                return False
        elif update_if_old and config.AUTO_UPDATE_OLLAMA and is_outdated():
            _STATE["action"] = "update"
            _emit("Ollama wird aktualisiert (zu alt für Function-Calling) …")
            _run_installer()

        # Dienst starten und auf Erreichbarkeit warten.
        from . import local_llm
        local_llm.ensure_running(timeout=40)
        _emit("Ollama bereit.")
        return True
    finally:
        _STATE["busy"] = False
        _lock.release()


def provision_async(**kwargs) -> None:
    """Startet provision() im Hintergrund (falls nicht schon laufend)."""
    if _STATE["busy"]:
        return
    threading.Thread(target=lambda: provision(**kwargs), daemon=True).start()
