"""Liest die Ollama-Modell-Bibliothek aus und schreibt catalog/models.json.

Wird woechentlich per GitHub-Action ausgefuehrt (siehe .github/workflows/
update-catalog.yml). Die App holt sich die JSON dann automatisch.

Hinweis: Das ist Web-Scraping -- aendert Ollama das HTML, muss der Parser
angepasst werden. Eine Sicherung verhindert, dass bei einem Fehlschlag eine
kaputte/leere Liste committed wird (Mindestanzahl Modelle).
"""
from __future__ import annotations

import html
import json
import re
import sys
import urllib.request
from pathlib import Path

URL = "https://ollama.com/library?sort=popular"
OUT = Path(__file__).resolve().parents[1] / "catalog" / "models.json"
MAX_MODELS = 70      # die beliebtesten -- haelt die Liste handhabbar
MIN_ENTRIES = 25     # Sicherung: darunter wird NICHT geschrieben


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 PrivacyAgent-Catalog"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def _tier(params: float) -> str:
    if params < 4:
        return "klein"
    if params <= 13:
        return "mittel"
    return "groß"


def _gb(params: float) -> str:
    g = max(0.3, params * 0.67)  # grobe Schaetzung fuer q4-Modelle
    return f"~{g:.1f} GB" if g < 10 else f"~{g:.0f} GB"


def scrape() -> list[dict]:
    page = _fetch(URL)
    # An den Modell-Links aufteilen; jeder Block ist eine Modell-Karte.
    chunks = re.split(r'href="/library/', page)
    out: list[dict] = []
    seen: set[str] = set()
    for chunk in chunks[1:]:
        nm = re.match(r'([a-zA-Z0-9._-]+)["/?]', chunk)
        if not nm:
            continue
        name = nm.group(1)
        if name in seen:
            continue
        seen.add(name)
        if len(seen) > MAX_MODELS:
            break

        # Beschreibung: erster <p>-Text in der Karte.
        desc = ""
        dm = re.search(r"<p[^>]*>(.*?)</p>", chunk, re.S)
        if dm:
            desc = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", dm.group(1)))).strip()[:170]

        # Groessen-Pills (z.B. 7b, 1.5b) im Karten-Anfang. NUR Milliarden ("b") --
        # Millionen-Werte ("M") sind hier meist Download-Zahlen, keine Groessen.
        sizes = []
        for sm in re.finditer(r">\s*(\d+(?:\.\d+)?)\s*[bB]\s*<", chunk[:2000]):
            p = float(sm.group(1))
            if 0.1 <= p <= 2000:  # plausible Modellgroesse
                sizes.append(sm.group(1).lower() + "b")
        sizes = list(dict.fromkeys(sizes))

        if "embed" in name:
            out.append({"name": name, "label": name, "size": "klein",
                        "tier": "spezial", "description": desc or "Embedding-Modell."})
            continue
        for s in sizes:
            p = float(s[:-1])
            out.append({
                "name": f"{name}:{s}",
                "label": f"{name} ({s})",
                "size": _gb(p),
                "tier": _tier(p),
                "description": desc,
            })
    return out


def main() -> int:
    try:
        models = scrape()
    except Exception as exc:  # noqa: BLE001
        print(f"Scraping fehlgeschlagen: {exc}", file=sys.stderr)
        return 1
    if len(models) < MIN_ENTRIES:
        print(f"Nur {len(models)} Eintraege -- zu wenig, breche ab "
              "(HTML evtl. geaendert).", file=sys.stderr)
        return 1
    OUT.write_text(
        json.dumps({"_hinweis": "Automatisch aus ollama.com/library erzeugt "
                    "(woechentlich). Manuell pflegbar, wird aber ueberschrieben.",
                    "models": models}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"{len(models)} Modell-Eintraege geschrieben -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
