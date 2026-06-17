"""Start-/Download-Hilfe fuer alternative lokale KI-Server (ohne Ollama).

Deckt OpenAI-kompatible lokale Server ab. Pro Eintrag: Standard-Adresse/Port und
wie er gestartet wird:

  * "file" (llamafile): EINE Datei -- wird bei Bedarf heruntergeladen und direkt
    als OpenAI-Server gestartet. Der einzige Fall, der wirklich vollautomatisch
    "herunterladen & starten" kann.
  * "app" (GPT4All / LM Studio / Jan): GUI-Apps. Wir starten eine *installierte*
    App (LM Studio zusaetzlich headless via `lms server start`). Ist sie nicht
    installiert, oeffnen wir die Download-Seite -- ein stilles Installieren samt
    Aktivieren des (in der App verborgenen) API-Servers ist nicht zuverlaessig.
"""
from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import threading
from pathlib import Path
from typing import Optional

from . import config
from ._proc import no_window

# id -> Standardwerte. "auto": file | app | none(=nur Adresse eintragen)
PRESETS: dict[str, dict] = {
    "llamafile": {"label": "llamafile (eine Datei, ohne Installation)",
                  "url": "http://localhost:8080/v1", "port": 8080, "auto": "file"},
    "gpt4all":   {"label": "GPT4All", "url": "http://localhost:4891/v1", "port": 4891, "auto": "app"},
    "lmstudio":  {"label": "LM Studio", "url": "http://localhost:1234/v1", "port": 1234, "auto": "app"},
    "jan":       {"label": "Jan", "url": "http://localhost:1337/v1", "port": 1337, "auto": "app"},
    "ollama":    {"label": "Ollama (OpenAI-Modus)", "url": "http://127.0.0.1:11434/v1",
                  "port": 11434, "auto": "none"},
}

_DOWNLOAD_PAGE = {
    "gpt4all": "https://gpt4all.io/",
    "lmstudio": "https://lmstudio.ai/",
    "jan": "https://jan.ai/",
}

# Kleines, breit lauffaehiges Standard-Modell als llamafile (~2,6 GB, Q6_K).
# Per Umgebungsvariable / Override austauschbar, falls sich die URL aendert.
_LLAMAFILE_DEFAULT_URL = (
    "https://huggingface.co/Mozilla/Llama-3.2-3B-Instruct-llamafile/"
    "resolve/main/Llama-3.2-3B-Instruct.Q6_K.llamafile"
)

_STATE = {"busy": False, "message": ""}


def presets() -> list[dict]:
    return [{"id": k, "label": v["label"], "url": v["url"], "port": v["port"], "auto": v["auto"]}
            for k, v in PRESETS.items()]


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


# --- App-Erkennung (best effort, mehrere uebliche Orte je OS) ------------
def _app_candidates(kind: str) -> list[str]:
    sysname = platform.system()
    home = Path.home()
    found: list[str] = []

    for name in {"gpt4all": ["gpt4all", "chat"], "lmstudio": ["lm-studio", "lms"],
                 "jan": ["jan"]}.get(kind, []):
        w = shutil.which(name)
        if w:
            found.append(w)

    if sysname == "Windows":
        la = os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local"))
        pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        rel = {
            "gpt4all": [Path(home, "gpt4all", "bin", "chat.exe"),
                        Path(la, "Programs", "gpt4all", "bin", "chat.exe"),
                        Path(pf, "gpt4all", "bin", "chat.exe")],
            "lmstudio": [Path(la, "Programs", "lm-studio", "LM Studio.exe"),
                         Path(home, ".lmstudio", "bin", "lms.exe")],
            "jan": [Path(la, "Programs", "jan", "Jan.exe"), Path(pf, "Jan", "Jan.exe")],
        }.get(kind, [])
        found += [str(p) for p in rel if p.exists()]
    elif sysname == "Darwin":
        app = {"gpt4all": "gpt4all.app", "lmstudio": "LM Studio.app", "jan": "Jan.app"}.get(kind)
        if app and (Path("/Applications") / app).exists():
            found.append(str(Path("/Applications") / app))
    return found


def _start_detached(args: list[str]) -> bool:
    try:
        subprocess.Popen(args, **no_window())
        return True
    except OSError:
        return False


def _launch_app(kind: str) -> Optional[str]:
    # LM Studio kann den API-Server headless starten -- das ist der beste Weg.
    if kind == "lmstudio":
        lms = shutil.which("lms") or next(
            (c for c in _app_candidates("lmstudio") if c.lower().endswith("lms.exe")), None)
        if lms and _start_detached([lms, "server", "start"]):
            return lms
    for path in _app_candidates(kind):
        if path.lower().endswith("lms.exe"):
            continue  # nur als CLI sinnvoll (oben behandelt)
        if platform.system() == "Darwin" and path.endswith(".app"):
            if _start_detached(["open", path]):
                return path
        elif _start_detached([path]):
            return path
    return None


# --- llamafile: herunterladen & starten ---------------------------------
def _llamafile_path() -> Path:
    d = config.data_dir() / "runtimes"
    d.mkdir(parents=True, exist_ok=True)
    name = "model.llamafile" + (".exe" if os.name == "nt" else "")
    return d / name


def _start_llamafile() -> bool:
    p = _llamafile_path()
    return _start_detached([str(p), "--server", "--nobrowser",
                            "--host", "127.0.0.1", "--port", "8080"])


def _download_and_start_llamafile() -> None:
    _STATE.update(busy=True, message="Lade llamafile (~2,6 GB) – das dauert beim ersten Mal …")
    try:
        import requests

        p = _llamafile_path()
        if not p.exists():
            url = getattr(config, "LLAMAFILE_URL", "") or _LLAMAFILE_DEFAULT_URL
            tmp = p.with_suffix(p.suffix + ".part")
            with requests.get(url, stream=True, timeout=900) as r:
                r.raise_for_status()
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        fh.write(chunk)
            tmp.rename(p)
            if os.name != "nt":
                os.chmod(p, 0o755)
        _STATE["message"] = "Starte llamafile …"
        ok = _start_llamafile()
        _STATE["message"] = ("llamafile gestartet – Server auf http://localhost:8080/v1."
                             if ok else "Konnte llamafile nicht starten.")
    except Exception as exc:  # noqa: BLE001  Netz-/Dateifehler dem Nutzer zeigen
        _STATE["message"] = f"Fehler: {exc}"
    finally:
        _STATE["busy"] = False


def launch(kind: str) -> dict:
    """Startet den gewuenschten Server (bzw. laedt llamafile / oeffnet Download-Seite)."""
    pre = PRESETS.get(kind)
    if not pre:
        return {"ok": False, "message": "Unbekannter Server."}
    if _port_open(pre["port"]):
        return {"ok": True, "running": True, "url": pre["url"], "message": "Server läuft bereits. ✅"}

    auto = pre["auto"]
    if auto == "file":  # llamafile
        if _STATE["busy"]:
            return {"ok": True, "busy": True, "message": _STATE["message"]}
        if _llamafile_path().exists():
            ok = _start_llamafile()
            return {"ok": ok, "url": pre["url"],
                    "message": "llamafile gestartet (Server auf :8080)." if ok
                               else "Konnte llamafile nicht starten."}
        threading.Thread(target=_download_and_start_llamafile, daemon=True).start()
        return {"ok": True, "busy": True,
                "message": "Lade llamafile herunter und starte danach automatisch …"}

    if auto == "app":
        path = _launch_app(kind)
        if path:
            note = ("LM Studio-Server wird gestartet …" if kind == "lmstudio"
                    else f"{pre['label']} gestartet – bitte einmalig den API-Server in der App aktivieren.")
            return {"ok": True, "launched": True, "url": pre["url"], "message": note}
        return {"ok": False, "needs_install": True, "download_url": _DOWNLOAD_PAGE.get(kind),
                "message": f"{pre['label']} ist nicht installiert – Download-Seite wird geöffnet."}

    return {"ok": True, "url": pre["url"], "message": "Adresse eingetragen."}


def launch_status() -> dict:
    return dict(_STATE)
