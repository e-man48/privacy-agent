"""Einrichtungs-Assistent: installiert die lokale KI beim ersten Start.

Aufgaben:
  1. Hardware erkennen (RAM, grob die GPU) und passendes Modell waehlen.
  2. Pruefen, ob Ollama installiert ist -- falls nicht, installieren.
  3. Das gewaehlte Modell herunterladen ("ollama pull").

Gibt Fortschritt als JSON-Zeilen auf stdout aus, damit die Tauri-GUI einen
Fortschrittsbalken anzeigen kann. Plattformuebergreifend (Windows/macOS/Linux).
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request

OLLAMA_HOST = "http://127.0.0.1:11434"


def emit(stage: str, message: str, progress: float | None = None, **extra) -> None:
    """Eine Fortschrittsmeldung als JSON-Zeile (von der GUI gelesen).

    ensure_ascii=True (Standard): Sonderzeichen werden als \\uXXXX kodiert ->
    die Ausgabe ist immer reines ASCII/gueltiges UTF-8, unabhaengig von der
    Windows-Konsolen-Codepage (cp1252). Sonst: 'stream did not contain valid UTF-8'.
    """
    payload = {"stage": stage, "message": message, "progress": progress, **extra}
    print(json.dumps(payload), flush=True)


# --- 1. Hardware erkennen + Modell waehlen ------------------------------
def total_ram_gb() -> float:
    try:
        if hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9
    except (ValueError, OSError):
        pass
    # Windows-Fallback ueber ctypes.
    if os.name == "nt":
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return stat.ullTotalPhys / 1e9
    return 8.0  # vorsichtige Annahme


def has_usable_gpu() -> bool:
    """Grobe Erkennung einer fuer KI brauchbaren GPU (NVIDIA-CUDA oder Apple-
    Silicon/Metal). Andere (Intel-/AMD-iGPUs) nutzt Ollama kaum -> als CPU werten.
    """
    # NVIDIA: nvidia-smi vorhanden?
    if shutil.which("nvidia-smi"):
        return True
    # Apple Silicon (arm64-Mac) -> Metal-GPU.
    if platform.system() == "Darwin" and platform.machine().lower() in ("arm64", "aarch64"):
        return True
    # Windows: dedizierte NVIDIA/AMD-GPU im Geraetenamen?
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "name"],
                capture_output=True, text=True, timeout=6,
                creationflags=0x08000000,
            ).stdout.lower()
            return "nvidia" in out or "geforce" in out or "rtx" in out or "radeon" in out
        except Exception:
            return False
    # Linux: NVIDIA/AMD per lspci?
    if shutil.which("lspci"):
        try:
            out = subprocess.run(["lspci"], capture_output=True, text=True, timeout=6).stdout.lower()
            return "nvidia" in out or "radeon" in out
        except Exception:
            return False
    return False


def choose_model(ram_gb: float, gpu: bool) -> str:
    """Waehlt das Modell anhand von RAM UND GPU.

    Ohne brauchbare GPU laeuft alles auf der CPU -- dort sind kleinere Modelle
    deutlich fluessiger, daher bewusst zurueckhaltender.
    """
    if gpu:
        if ram_gb < 8:
            return "qwen2.5:3b"
        if ram_gb < 16:
            return "qwen2.5:7b"
        return "qwen2.5:14b"
    # Nur-CPU: klein halten, damit es benutzbar bleibt.
    if ram_gb < 8:
        return "qwen2.5:1.5b"
    if ram_gb < 16:
        return "qwen2.5:3b"
    return "qwen2.5:7b"


# --- 2. Ollama installieren ---------------------------------------------
def find_ollama() -> "str | None":
    """Findet ollama.exe -- auch wenn es (noch) nicht im PATH des laufenden
    Prozesses steht (typisch direkt nach der Installation auf Windows)."""
    found = shutil.which("ollama")
    if found:
        return found
    if os.name == "nt":
        candidates = []
        for base in (os.environ.get("LOCALAPPDATA", ""),
                     os.environ.get("ProgramFiles", ""),
                     os.environ.get("ProgramW6432", "")):
            if base:
                candidates.append(os.path.join(base, "Programs", "Ollama", "ollama.exe"))
                candidates.append(os.path.join(base, "Ollama", "ollama.exe"))
        for cand in candidates:
            if os.path.isfile(cand):
                return cand
    return None


def ollama_installed() -> bool:
    return find_ollama() is not None


def _no_window() -> dict:
    """Unterdrueckt das DOS-Fenster bei Unterprozessen (Windows)."""
    return {"creationflags": 0x08000000} if os.name == "nt" else {}


def _download(url: str, dest: str, timeout: int = 180) -> None:
    """HTTPS-Download mit verlaesslicher Zertifikatspruefung (requests/certifi).

    Wichtig im gebuendelten Programm: der eingebettete Python findet sonst die
    System-Wurzelzertifikate nicht -> CERTIFICATE_VERIFY_FAILED. requests bringt
    ueber certifi ein eigenes CA-Paket mit.
    """
    import requests

    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 16):
                fh.write(chunk)


def _http_text(url: str, timeout: int = 30) -> str:
    import requests

    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text


def install_ollama() -> bool:
    system = platform.system()
    emit("install_ollama", f"Installiere Ollama fuer {system} ...", 0.3)
    try:
        if system == "Darwin":  # macOS
            subprocess.run(["brew", "install", "ollama"], check=True)
        elif system == "Linux":
            # Offizielles Installationsskript.
            script = _http_text("https://ollama.com/install.sh")
            subprocess.run(["sh", "-c", script], check=True)
        elif system == "Windows":
            url = "https://ollama.com/download/OllamaSetup.exe"
            tmp = os.path.join(os.environ.get("TEMP", "."), "OllamaSetup.exe")
            emit("install_ollama", "Lade Ollama-Installer herunter ...", 0.4)
            _download(url, tmp)
            emit("install_ollama", "Starte Ollama-Installer (still) ...", 0.6)
            subprocess.run([tmp, "/VERYSILENT", "/NORESTART"], check=True, **_no_window())
        else:
            emit("error", f"Nicht unterstuetztes System: {system}")
            return False
    except Exception as exc:  # Netz-/SSL-/Installer-Fehler sauber melden
        emit("error", f"Ollama-Installation fehlgeschlagen: {exc}")
        return False
    return True


def ensure_ollama_running() -> bool:
    """Stellt sicher, dass der Ollama-Dienst laeuft.

    Auf Windows startet Ollama meist von selbst (Tray). Wir warten daher
    ausreichend lange auf die API und stossen den Dienst -- ueber den gefundenen
    Pfad -- nur an, falls er nach ein paar Versuchen noch nicht erreichbar ist.
    """
    import requests

    exe = find_ollama()
    for attempt in range(15):  # ~30 Sekunden Geduld
        try:
            requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
            return True
        except requests.RequestException:
            pass
        # Nach dem zweiten Fehlversuch selbst starten (falls noch nicht laeuft).
        if attempt == 1 and exe:
            try:
                subprocess.Popen(
                    [exe, "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **_no_window(),
                )
            except OSError:
                pass
        time.sleep(2)
    return False


# --- 3. Modell herunterladen --------------------------------------------
def pull_model(model: str, lo: float = 0.55, hi: float = 0.92) -> bool:
    """Laedt ein Modell ueber Ollamas Streaming-API mit ECHTEM Fortschritt.

    Die API liefert laufend completed/total -> fluessiger Prozentbalken
    (statt der CLI, die nur pro fertiger Schicht meldet). Der Fortschritt wird
    in den Bereich [lo, hi] des Gesamtbalkens gemappt.
    """
    import requests

    emit("pull_model", f"Lade Modell '{model}' ...", lo)
    try:
        with requests.post(
            f"{OLLAMA_HOST}/api/pull",
            json={"model": model, "stream": True},
            stream=True,
            timeout=(10, 300),
        ) as r:
            r.raise_for_status()
            for raw in r.iter_lines():
                if not raw:
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("error"):
                    emit("error", f"Modell-Download fehlgeschlagen: {msg['error']}")
                    return False
                status = msg.get("status", "")
                total = msg.get("total")
                completed = msg.get("completed")
                if total and completed is not None:
                    frac = completed / total
                    gb_done, gb_total = completed / 1e9, total / 1e9
                    emit(
                        "pull_model",
                        f"Lade '{model}' – {frac * 100:.0f} % "
                        f"({gb_done:.1f}/{gb_total:.1f} GB)",
                        round(lo + (hi - lo) * frac, 3),
                    )
                elif status:
                    # Status ohne Prozent (z.B. "verifying", "success"):
                    # nur Text, Balken NICHT zuruecksetzen (progress=None).
                    emit("pull_model", status)
            return True
    except requests.RequestException as exc:
        emit("error", f"Modell-Download fehlgeschlagen: {exc}")
        return False


def _user_settings_path() -> str:
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME",
                              os.path.join(os.path.expanduser("~"), ".local", "share"))
    d = os.path.join(base, "PrivacyAgent")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "user_settings.json")


def _persist_local_model(model: str) -> None:
    """Speichert das gewaehlte Modell in den Nutzereinstellungen (Fallback)."""
    path = _user_settings_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    data["local_model"] = model
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def setup_runtimes() -> None:
    """Richtet Node.js und uv ein, damit externe Skills (MCP) sofort laufen.

    Teil des Installationsprozesses: viele Skills brauchen npx (Node) oder uvx
    (uv). Best effort -- schlaegt es fehl (z.B. kein Netz), bleibt die App nutzbar
    und der Nutzer kann Skills spaeter nachruesten.
    """
    try:
        from agent import runtimes
    except Exception as exc:  # Bundle-/Importfehler nicht fatal
        emit("runtimes", f"Skill-Laufzeiten uebersprungen ({exc}).")
        return
    for name, label, prog in (("node", "Node.js", 0.94), ("uv", "uv (Python)", 0.97)):
        try:
            emit("runtimes", f"Richte {label} fuer Skills ein ...", prog)
            runtimes.ensure(name, lambda m: emit("runtimes", m))
        except Exception as exc:  # noqa: BLE001
            emit("runtimes", f"{label} uebersprungen ({exc}) -- Skills spaeter nachruestbar.")


def main() -> int:
    emit("detect", "Erkenne Hardware ...", 0.05)
    ram = total_ram_gb()
    gpu = has_usable_gpu()
    model = choose_model(ram, gpu)
    hw = "GPU" if gpu else "nur CPU"
    emit("detect", f"{ram:.0f} GB RAM, {hw} -> Modell '{model}'",
         0.1, model=model, ram_gb=ram, gpu=gpu)

    if not ollama_installed():
        if not install_ollama():
            return 1
    else:
        emit("install_ollama", "Ollama bereits installiert.", 0.5)

    if not ensure_ollama_running():
        emit("error", "Ollama-Dienst konnte nicht gestartet werden.")
        return 1

    # Hauptmodell: Fortschritt 0.55 .. 0.85.
    if not pull_model(model, lo=0.55, hi=0.85):
        emit("error", f"Modell '{model}' konnte nicht geladen werden.")
        return 1

    # Dem laufenden Backend das gewaehlte Modell mitteilen -- sonst prueft es
    # weiter sein Standard-Modell und 'Modell bereit?' bleibt faelschlich auf
    # nein (der Assistent koennte dann nicht weiter).
    try:
        import requests
        requests.post("http://127.0.0.1:8765/model/set", json={"name": model}, timeout=5)
    except Exception:  # Backend evtl. nicht erreichbar
        pass
    _persist_local_model(model)  # spaetestens beim naechsten Start aktiv

    # Embedding-Modell fuer das semantische Gedaechtnis (klein, ~270 MB).
    # Nicht kritisch: schlaegt es fehl, faellt das Gedaechtnis auf die
    # lexikalische Suche zurueck. Fortschritt 0.85 .. 0.92.
    if not pull_model("nomic-embed-text", lo=0.85, hi=0.92):
        emit("pull_embed", "Embedding-Modell uebersprungen (Gedaechtnis bleibt lexikalisch).", 0.92)

    # Laufzeiten fuer externe Skills (Node/uv) gleich mit einrichten. Best effort.
    setup_runtimes()

    emit("done", "Einrichtung abgeschlossen. Die lokale KI ist bereit.", 1.0, model=model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
