"""Registratur aller verfuegbaren Werkzeuge.

Ein Werkzeug ist eine Funktion plus Metadaten. `leaves_device=True` markiert
Werkzeuge, die Daten nach aussen geben (z.B. Web-Suche) -- der Router behandelt
diese wie eine Cloud-Eskalation und fragt vorher um Erlaubnis.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class Tool:
    name: str
    description: str
    func: Callable[..., str]
    leaves_device: bool = False      # gibt Daten nach aussen (z.B. Web-Suche)
    requires_consent: bool = False   # braucht ausdrueckliche Nutzer-Genehmigung


# --- Dateien lesen (lokal) ----------------------------------------------
def _read_file(path: str, max_chars: int = 20000) -> str:
    p = Path(path).expanduser()
    if not p.is_file():
        return f"FEHLER: Datei nicht gefunden: {path}"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"FEHLER beim Lesen: {exc}"
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... [gekuerzt]"
    return text


def _list_dir(path: str = ".") -> str:
    p = Path(path).expanduser()
    if not p.is_dir():
        return f"FEHLER: Kein Verzeichnis: {path}"
    entries = sorted(e.name + ("/" if e.is_dir() else "") for e in p.iterdir())
    return "\n".join(entries) or "(leer)"


# --- Code lokal ausfuehren (eingeschraenkt) -----------------------------
def _run_python(code: str) -> str:
    """Fuehrt Python-Code in der Sandbox aus (siehe agent/sandbox.py).

    Die Ausfuehrung ist genehmigungspflichtig (requires_consent) und laeuft in
    der staerksten verfuegbaren Isolationsstufe. Das Ergebnis nennt die Stufe,
    damit transparent ist, wie stark der Code isoliert war.
    """
    from .. import sandbox

    result = sandbox.run(code)
    stufe = "Docker" if result.tier == "docker" else "eingeschraenkt"
    return f"[Sandbox: {stufe}]\n{result.output}"


# --- Web-Suche (verlaesst das Geraet!) ----------------------------------
def _web_search(query: str, max_results: int = 5) -> str:
    """Einfache Web-Suche ueber die DuckDuckGo-HTML-Schnittstelle.

    ACHTUNG: Diese Anfrage verlaesst das Geraet. Der Router fragt deshalb
    vorher um Erlaubnis (leaves_device=True).
    """
    import requests
    from html.parser import HTMLParser

    class _LinkText(HTMLParser):
        def __init__(self):
            super().__init__()
            self.results: list[str] = []
            self._grab = False

        def handle_starttag(self, tag, attrs):
            if tag == "a" and ("class", "result__a") in attrs:
                self._grab = True

        def handle_data(self, data):
            if self._grab and data.strip():
                self.results.append(data.strip())
                self._grab = False

    try:
        r = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0 PrivacyAgent"},
            timeout=15,
        )
        r.raise_for_status()
    except requests.RequestException as exc:
        return f"FEHLER bei Web-Suche: {exc}"
    parser = _LinkText()
    parser.feed(r.text)
    titles = parser.results[:max_results]
    return "\n".join(f"- {t}" for t in titles) or "(keine Treffer)"


TOOLS: dict[str, Tool] = {
    "read_file": Tool(
        "read_file",
        "Liest den Inhalt einer lokalen Datei. Argument: path (str).",
        _read_file,
    ),
    "list_dir": Tool(
        "list_dir",
        "Listet den Inhalt eines lokalen Verzeichnisses. Argument: path (str).",
        _list_dir,
    ),
    "run_python": Tool(
        "run_python",
        "Fuehrt kurzen Python-Code in einer Sandbox aus und gibt die Ausgabe zurueck. Argument: code (str).",
        _run_python,
        requires_consent=True,
    ),
    "web_search": Tool(
        "web_search",
        "Sucht im Internet. ACHTUNG: verlaesst das Geraet. Argument: query (str).",
        _web_search,
        leaves_device=True,
        requires_consent=True,
    ),
}


def tool_descriptions() -> str:
    """Kompakte Beschreibung aller Werkzeuge fuer den System-Prompt."""
    lines = []
    for t in TOOLS.values():
        if t.leaves_device:
            flag = "  [VERLAESST GERAET - Genehmigung noetig]"
        elif t.requires_consent:
            flag = "  [Genehmigung noetig]"
        else:
            flag = ""
        lines.append(f"- {t.name}: {t.description}{flag}")
    return "\n".join(lines)


def run_tool(name: str, **kwargs) -> str:
    tool = TOOLS.get(name)
    if tool is None:
        return f"FEHLER: Unbekanntes Werkzeug '{name}'."
    return tool.func(**kwargs)
