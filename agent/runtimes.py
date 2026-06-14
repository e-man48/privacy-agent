"""Laufzeit-Verwaltung fuer externe Skills (MCP).

Viele MCP-Server brauchen Node.js (`npx`) oder uv (`uvx`). Damit Laien nichts
von Hand installieren muessen, erkennt und installiert dieses Modul beide --
ohne Admin-Rechte, lokal in den App-Datenordner.

  * Node.js: offizielles, vorgefertigtes Archiv wird heruntergeladen und in
    `<data>/runtimes/node` entpackt (kein Systemeingriff).
  * uv: offizieller Standalone-Installer (kein pip noetig).

`resolve()` findet einen Befehl im System-PATH oder in den verwalteten Orten.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

from . import config
from ._proc import no_window

NODE_VERSION = "v20.18.0"  # LTS


def runtimes_dir() -> Path:
    d = config.data_dir() / "runtimes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _node_bin_dirs() -> list[Path]:
    node = runtimes_dir() / "node"
    return [node, node / "bin"]  # Windows: Wurzel, Unix: bin/


def _uv_bin_dirs() -> list[Path]:
    home = Path.home()
    return [home / ".local" / "bin", home / ".cargo" / "bin"]


def _exe_names(command: str) -> list[str]:
    if os.name == "nt":
        if command in ("npx", "npm"):
            return [command + ".cmd", command + ".exe"]
        return [command + ".exe", command]
    return [command]


def resolve(command: str) -> Optional[str]:
    """Voller Pfad zu einem Befehl -- System-PATH zuerst, dann verwaltete Orte."""
    found = shutil.which(command)
    if found:
        return found
    search = _node_bin_dirs() if command in ("node", "npx", "npm") else _uv_bin_dirs()
    for directory in search:
        for name in _exe_names(command):
            cand = directory / name
            if cand.exists():
                return str(cand)
    return None


def available(command: str) -> bool:
    return resolve(command) is not None


def status() -> dict:
    return {
        "node": {"available": available("npx")},
        "uv": {"available": available("uvx")},
    }


# --- Installation -------------------------------------------------------
def _arch() -> str:
    m = platform.machine().lower()
    return {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(m, "x64")


def install_node(emit: Callable[[str], None]) -> None:
    system = platform.system()
    arch = _arch()
    if system == "Windows":
        fname = f"node-{NODE_VERSION}-win-{arch}.zip"
    elif system == "Darwin":
        fname = f"node-{NODE_VERSION}-darwin-{arch}.tar.gz"
    else:
        fname = f"node-{NODE_VERSION}-linux-{arch}.tar.xz"

    url = f"https://nodejs.org/dist/{NODE_VERSION}/{fname}"
    archive = runtimes_dir() / fname
    emit(f"Lade Node.js {NODE_VERSION} herunter …")
    # requests nutzt certifi -> verlaessliche TLS-Pruefung auch im Bundle.
    import requests

    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(archive, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 16):
                fh.write(chunk)

    emit("Entpacke Node.js …")
    if fname.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(runtimes_dir())
    else:
        with tarfile.open(archive) as t:
            t.extractall(runtimes_dir())

    extracted = next(p for p in runtimes_dir().iterdir()
                     if p.is_dir() and p.name.startswith("node-"))
    target = runtimes_dir() / "node"
    if target.exists():
        shutil.rmtree(target)
    extracted.rename(target)
    archive.unlink(missing_ok=True)
    emit("Node.js eingerichtet.")


def install_uv(emit: Callable[[str], None]) -> None:
    emit("Richte uv ein …")
    if os.name == "nt":
        cmd = ["powershell", "-ExecutionPolicy", "ByPass", "-NoProfile", "-Command",
               "irm https://astral.sh/uv/install.ps1 | iex"]
    else:
        cmd = ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"]
    subprocess.run(cmd, check=True, **no_window())
    emit("uv eingerichtet.")


def ensure(name: str, emit: Optional[Callable[[str], None]] = None) -> None:
    """Stellt sicher, dass eine Laufzeit vorhanden ist (installiert sie sonst)."""
    emit = emit or (lambda _m: None)
    if name == "node":
        if available("npx"):
            return emit("Node.js ist bereits vorhanden.")
        install_node(emit)
    elif name == "uv":
        if available("uvx"):
            return emit("uv ist bereits vorhanden.")
        install_uv(emit)
    else:
        raise ValueError(f"Unbekannte Laufzeit: {name}")
