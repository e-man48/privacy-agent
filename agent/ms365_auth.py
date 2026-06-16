"""Microsoft-365-Anmeldung (Geraete-Code) fuer den 'Outlook (Login)'-Skill.

Startet `npx @softeria/ms-365-mcp-server --login`, liest den Geraete-Code und
die URL aus der Ausgabe und oeffnet den Browser. Der Login-Prozess pollt im
Hintergrund weiter, bis der Nutzer im Browser bestaetigt hat; danach liegt das
Token im OS-Anmeldespeicher -- der spaeter gestartete Skill nutzt es automatisch.
"""
from __future__ import annotations

import re
import subprocess
import threading
import time
import webbrowser

from . import runtimes
from ._proc import no_window


def login(timeout: int = 25) -> dict:
    exe = runtimes.resolve("npx") or "npx"
    try:
        proc = subprocess.Popen(
            [exe, "-y", "@softeria/ms-365-mcp-server", "--login"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **no_window(),
        )
    except OSError as exc:
        return {"ok": False, "message": f"Konnte Anmeldung nicht starten: {exc}"}

    lines: list[str] = []
    found: dict[str, str] = {}

    def _reader() -> None:
        assert proc.stdout
        for line in proc.stdout:
            lines.append(line)
            if "url" not in found:
                u = re.search(r"https://\S*(?:devicelogin|microsoft\.com)\S*", line)
                if u:
                    found["url"] = u.group(0).rstrip(".,)")
            if "code" not in found and "code" in line.lower():
                c = re.search(r"\b([A-Z0-9]{6,12})\b", line)
                if c:
                    found["code"] = c.group(1)

    threading.Thread(target=_reader, daemon=True).start()

    deadline = time.time() + timeout
    while time.time() < deadline and not ("url" in found and "code" in found):
        time.sleep(0.4)

    url, code = found.get("url", ""), found.get("code", "")
    if url:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    return {
        "ok": bool(url or code),
        "url": url or "https://microsoft.com/devicelogin",
        "code": code,
        "raw": "".join(lines)[-600:],
    }
