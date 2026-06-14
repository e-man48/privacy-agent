"""Baut das Python-Backend zu EINEM eigenstaendigen Binary und legt es als
Tauri-Sidecar ab -- damit beim Nutzer kein Python noetig ist.

Ablauf:
  1. Host-Zielarchitektur ("target triple") von rustc ermitteln.
  2. PyInstaller buendelt launcher.py inkl. agent/ + setup/ zu einem Binary.
  3. Das Binary wird nach src-tauri/binaries/<name>-<triple>(.exe) kopiert --
     genau dieses Namensschema erwartet Tauri fuer externalBin.

Aufruf (im Projektordner, mit aktivierter venv):
    python build_sidecar.py

Voraussetzungen: pip install -r agent/requirements.txt  (enthaelt pyinstaller)
und eine Rust-Installation (rustup) fuer 'rustc'.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BIN_DIR = ROOT / "src-tauri" / "binaries"
NAME = "privacy-agent-backend"


def host_triple() -> str:
    """Ermittelt das Rust-Target-Triple des aktuellen Systems (z.B.
    x86_64-pc-windows-msvc), das Tauri an den Sidecar-Namen anhaengt."""
    try:
        out = subprocess.run(
            ["rustc", "-Vv"], capture_output=True, text=True, check=True
        ).stdout
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        sys.exit(f"rustc nicht gefunden -- bitte Rust installieren (https://rustup.rs). {exc}")
    for line in out.splitlines():
        if line.startswith("host:"):
            return line.split(":", 1)[1].strip()
    sys.exit("Konnte Target-Triple nicht aus 'rustc -Vv' lesen.")


def build() -> None:
    triple = host_triple()
    ext = ".exe" if os.name == "nt" else ""

    print(f"==> Baue Sidecar fuer {triple} ...")
    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller",
            "--onefile", "--noconfirm", "--clean",
            "--name", NAME,
            "--paths", str(ROOT),
            # Dynamisch geladene Module, die PyInstaller sonst uebersieht:
            "--collect-all", "uvicorn",
            "--collect-all", "fastapi",
            "--collect-all", "pydantic",
            "--collect-all", "anthropic",
            "--hidden-import", "agent.main",
            "--hidden-import", "setup.first_run",
            str(ROOT / "launcher.py"),
        ],
        check=True,
        cwd=ROOT,
    )

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    src = ROOT / "dist" / f"{NAME}{ext}"
    dst = BIN_DIR / f"{NAME}-{triple}{ext}"
    shutil.copy2(src, dst)
    print(f"\n==> Fertig. Sidecar liegt unter:\n    {dst}")
    print("    Jetzt 'npm run dev' bzw. 'npm run build' ausfuehren.")


if __name__ == "__main__":
    build()
