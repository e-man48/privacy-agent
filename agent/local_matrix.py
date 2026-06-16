"""Lokaler Matrix-Homeserver (Conduit) ueber Docker -- fuer Nutzer OHNE NAS.

Hinweis/ehrliche Einordnung:
  * Es gibt keine zuverlaessige native Windows-Binaerdatei fuer schlanke Matrix-
    Homeserver -- daher laeuft der lokale Server hier ueber Docker (plattform-
    uebergreifend). Voraussetzung: Docker ist installiert.
  * Ein lokaler Server ist nur online, solange dieser PC laeuft. Fuer 'von
    unterwegs erreichbar' ist ein NAS/Server (z.B. Synapse) die bessere Wahl.

Verwendet das gut dokumentierte Conduit-Image (matrixconduit/matrix-conduit).
Registrierung neuer Konten erfolgt mit einem Registrierungs-Token (wird erzeugt
und angezeigt) ueber einen Matrix-Client wie Element.
"""
from __future__ import annotations

import json
import secrets
import shutil
import subprocess

from . import config
from ._proc import no_window

CONTAINER = "pa-matrix"
IMAGE = "matrixconduit/matrix-conduit:latest"
PORT = 6167
_STATE_PATH = config.data_dir() / "local_matrix.json"


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True,
                              timeout=5, **no_window()).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _load() -> dict:
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    _STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _running() -> bool:
    try:
        out = subprocess.run(["docker", "ps", "--filter", f"name={CONTAINER}",
                              "--format", "{{.Names}}"],
                             capture_output=True, text=True, timeout=6, **no_window()).stdout
        return CONTAINER in out
    except (OSError, subprocess.TimeoutExpired):
        return False


def status() -> dict:
    if not docker_available():
        return {"docker": False, "running": False}
    data = _load()
    return {
        "docker": True,
        "running": _running(),
        "server_name": data.get("server_name", ""),
        "url": f"http://localhost:{PORT}",
        "token": data.get("token", ""),
    }


def start(server_name: str, emit) -> bool:
    """Startet den lokalen Conduit-Server (Docker). Erzeugt ggf. ein Token."""
    if not docker_available():
        emit("Docker ist nicht verfuegbar. Bitte Docker Desktop installieren.")
        return False
    server_name = (server_name or "localhost").strip()

    data = _load()
    token = data.get("token") or secrets.token_urlsafe(16)
    data.update(server_name=server_name, token=token)
    _save(data)

    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True, **no_window())
    emit(f"Starte lokalen Matrix-Server '{server_name}' (Docker) ...")
    cmd = [
        "docker", "run", "-d", "--name", CONTAINER, "--restart", "unless-stopped",
        "-p", f"{PORT}:{PORT}",
        "-v", "pa-matrix-data:/var/lib/matrix-conduit",
        "-e", f"CONDUIT_SERVER_NAME={server_name}",
        "-e", "CONDUIT_DATABASE_PATH=/var/lib/matrix-conduit",
        "-e", "CONDUIT_DATABASE_BACKEND=rocksdb",
        "-e", f"CONDUIT_PORT={PORT}",
        "-e", "CONDUIT_ALLOW_REGISTRATION=true",
        "-e", f"CONDUIT_REGISTRATION_TOKEN={token}",
        "-e", "CONDUIT_ALLOW_FEDERATION=false",
        "-e", "CONDUIT_MAX_REQUEST_SIZE=20000000",
        "-e", "CONDUIT_ADDRESS=0.0.0.0",
        IMAGE,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, **no_window())
    except (OSError, subprocess.TimeoutExpired) as exc:
        emit(f"Start fehlgeschlagen: {exc}")
        return False
    if r.returncode != 0:
        emit(f"Start fehlgeschlagen: {r.stderr.strip()[:200]}")
        return False
    emit("Lokaler Matrix-Server laeuft.")
    return True


def stop() -> bool:
    try:
        subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True,
                       timeout=15, **no_window())
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False
