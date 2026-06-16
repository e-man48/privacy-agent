"""Tailscale per Ein-Klick einrichten -- Installieren, Anmelden, Status.

So muss der Nutzer den 'PC muss im Tailnet sein'-Schritt nicht von Hand machen.
Auf Windows wird der offizielle MSI-Installer geladen und ausgefuehrt (UAC-
Bestaetigung noetig); die Anmeldung laeuft ueber den Browser ('tailscale up').
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import threading
import webbrowser

from ._proc import no_window


def path() -> str | None:
    """Findet die tailscale-CLI -- PATH oder Standard-Installationsort."""
    found = shutil.which("tailscale")
    if found:
        return found
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramW6432", r"C:\Program Files")):
            cand = os.path.join(base, "Tailscale", "tailscale.exe")
            if os.path.isfile(cand):
                return cand
    return None


def status() -> dict:
    """Zustand: installiert? angemeldet? Tailnet-IP/-Name?"""
    exe = path()
    if not exe:
        return {"installed": False, "state": "absent", "ip": "", "name": ""}
    try:
        out = subprocess.run([exe, "status", "--json"], capture_output=True,
                             text=True, timeout=8, **no_window()).stdout
        data = json.loads(out)
        state = data.get("BackendState", "unknown")  # Running | NeedsLogin | Stopped
        me = data.get("Self") or {}
        ips = me.get("TailscaleIPs") or []
        ip = next((i for i in ips if ":" not in i), ips[0] if ips else "")
        name = (me.get("DNSName") or "").rstrip(".")
        return {"installed": True, "state": state, "ip": ip, "name": name,
                "logged_in": state == "Running"}
    except Exception:  # noqa: BLE001
        return {"installed": True, "state": "unknown", "ip": "", "name": ""}


def _latest_msi_url() -> str | None:
    import requests

    arch = "amd64" if platform.machine().lower() in ("amd64", "x86_64") else "x86"
    try:
        data = requests.get("https://pkgs.tailscale.com/stable/?mode=json", timeout=15).json()
        msis = data.get("MSIs") or {}
        if arch in msis:
            return "https://pkgs.tailscale.com/stable/" + msis[arch]
        ver = data.get("Version") or data.get("TarballsVersion")
        if ver:
            return f"https://pkgs.tailscale.com/stable/tailscale-setup-{ver}-{arch}.msi"
    except Exception:  # noqa: BLE001
        pass
    return None


def install(emit) -> bool:
    """Installiert Tailscale (nur Windows automatisch; sonst Hinweis)."""
    if platform.system() != "Windows":
        emit("Bitte Tailscale manuell installieren: https://tailscale.com/download")
        return False
    url = _latest_msi_url()
    if not url:
        emit("Konnte den Tailscale-Installer nicht finden.")
        return False
    import requests

    tmp = os.path.join(os.environ.get("TEMP", "."), "tailscale-setup.msi")
    emit("Lade Tailscale herunter ...")
    try:
        with requests.get(url, stream=True, timeout=180) as r:
            r.raise_for_status()
            with open(tmp, "wb") as fh:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    fh.write(chunk)
    except requests.RequestException as exc:
        emit(f"Download fehlgeschlagen: {exc}")
        return False
    emit("Starte Installer – bitte die Windows-Abfrage (UAC) bestaetigen ...")
    try:
        subprocess.run(["msiexec", "/i", tmp, "/passive", "/norestart"], **no_window())
    except OSError as exc:
        emit(f"Installation fehlgeschlagen: {exc}")
        return False
    emit("Tailscale installiert.")
    return True


def login() -> tuple[bool, str]:
    """Startet die Anmeldung ('tailscale up') und oeffnet den Browser-Login."""
    exe = path()
    if not exe:
        return False, "Tailscale ist nicht installiert."
    try:
        proc = subprocess.Popen([exe, "up"], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, **no_window())
    except OSError as exc:
        return False, str(exc)

    def _reader() -> None:
        for line in proc.stdout:  # type: ignore[union-attr]
            if "login.tailscale.com" in line:
                url = line.strip().split()[-1]
                try:
                    webbrowser.open(url)
                except Exception:  # noqa: BLE001
                    pass

    threading.Thread(target=_reader, daemon=True).start()
    return True, "Anmeldung gestartet – ggf. im Browser bestaetigen."
