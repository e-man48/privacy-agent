"""Einheitlicher Einstiegspunkt fuer das gebuendelte Sidecar-Binary.

Statt zweier getrennter Python-Aufrufe gibt es EIN Binary mit zwei Modi:

    privacy-agent-backend serve   -> startet das FastAPI-Backend (Standard)
    privacy-agent-backend setup   -> fuehrt den Einrichtungs-Assistenten aus

So muss die Tauri-Huelle nur ein einziges externes Binary kennen, und beim
Nutzer ist keine Python-Installation noetig (PyInstaller bettet den Interpreter
mit ein).
"""
from __future__ import annotations

import sys


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "serve"

    if mode == "setup":
        from setup.first_run import main as setup_main
        return setup_main()

    if mode == "serve":
        from agent.main import run
        run()
        return 0

    print(f"Unbekannter Modus: {mode!r}. Erlaubt: serve | setup", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
