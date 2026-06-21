"""Persistentes Gedaechtnis des Agenten.

Speichert gelernte Fakten, Nutzervorlieben und Betriebsregeln dauerhaft auf dem
Geraet (JSONL im Nutzer-Datenordner -- verlaesst das Geraet nicht).

Arten (kind):
  - "fact"       : ein gemerkter Sachverhalt
  - "preference" : eine Vorliebe des Nutzers
  - "guideline"  : eine Betriebsregel, die IMMER in den System-Prompt einfliesst
  - "outcome"    : Notiz zu einem Aufgabenergebnis (fuer Selbstreflexion)

Abruf erfolgt rein lexikalisch (Token-Ueberlappung) -- kein zusaetzliches
Embedding-Modell noetig, damit der lokale Betrieb leichtgewichtig bleibt.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

from . import config, embeddings

_VALID_KINDS = {"fact", "preference", "guideline", "outcome"}


@dataclass
class Memory:
    id: str
    timestamp: str
    kind: str
    text: str
    source: str  # "user" | "optimizer" | "auto"
    # Besitzer-Bereich: "shared" (fuer alle), "local" (GUI) oder eine Person-ID.
    owner: str = "shared"
    # Semantischer Vektor (lokal erzeugt); None, solange kein Embed-Modell da war.
    embedding: Optional[list[float]] = None


def _visible(m: "Memory", owner: Optional[str]) -> bool:
    """Sichtbar, wenn kein Bereich verlangt ist, der eigene oder geteilt."""
    return owner is None or m.owner == owner or m.owner == "shared"


def _read_all() -> list[Memory]:
    try:
        with open(config.MEMORY_PATH, "r", encoding="utf-8") as fh:
            return [Memory(**json.loads(line)) for line in fh if line.strip()]
    except FileNotFoundError:
        return []


def _write_all(items: list[Memory]) -> None:
    with open(config.MEMORY_PATH, "w", encoding="utf-8") as fh:
        for m in items:
            fh.write(json.dumps(asdict(m), ensure_ascii=False) + "\n")


def add(text: str, kind: str = "fact", source: str = "user", owner: str = "shared") -> Memory:
    if kind not in _VALID_KINDS:
        raise ValueError(f"Unbekannte Gedaechtnis-Art: {kind}")
    clean = text.strip()
    mem = Memory(
        id=uuid.uuid4().hex[:12],
        timestamp=datetime.now(timezone.utc).isoformat(),
        kind=kind,
        text=clean,
        source=source,
        owner=owner,
        embedding=embeddings.embed(clean) if embeddings.is_available() else None,
    )
    with open(config.MEMORY_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(mem), ensure_ascii=False) + "\n")
    export_markdown()  # lesbaren Markdown-Spiegel aktuell halten
    return mem


def all() -> list[Memory]:  # noqa: A003 (bewusst "all")
    return _read_all()


def by_kind(kind: str, owner: Optional[str] = None) -> list[Memory]:
    return [m for m in _read_all() if m.kind == kind and _visible(m, owner)]


def visible(owner: Optional[str]) -> list[Memory]:
    """Alle fuer einen Bereich sichtbaren Eintraege (eigener + geteilt)."""
    return [m for m in _read_all() if _visible(m, owner)]


def forget(mem_id: str) -> bool:
    items = _read_all()
    kept = [m for m in items if m.id != mem_id]
    if len(kept) == len(items):
        return False
    _write_all(kept)
    export_markdown()
    return True


# --- Markdown-Gedaechtnis (lesbar + von Hand editierbar) -----------------
# Spiegel des Gedaechtnisses als Markdown-Datei -- transparent (du siehst, was
# der Agent sich merkt) und editierbar (Datei aendern -> "aus Markdown neu laden").
_KIND_LABEL = {"guideline": "Regeln", "fact": "Fakten",
               "preference": "Vorlieben", "outcome": "Notizen"}
_LABEL_KIND = {v: k for k, v in _KIND_LABEL.items()}
_KIND_ORDER = ["guideline", "fact", "preference", "outcome"]


def _md_path():
    return config.data_dir() / "memory.md"


def export_markdown() -> None:
    """Schreibt das Gedaechtnis als lesbare Markdown-Datei (Spiegel des JSONL)."""
    items = _read_all()
    owners = sorted({m.owner for m in items}, key=lambda o: (o != "shared", o))
    lines = [
        "# Gedächtnis (Privacy-Agent)",
        "",
        "> Diese Datei ist von Hand editierbar. Aendere/loesche Zeilen und klicke in",
        "> der App auf **aus Markdown neu laden**. Die Ueberschriften",
        "> (`## Bereich:` / `### ... (kind)`) bitte stehen lassen.",
        "",
    ]
    for owner in owners:
        lines.append(f"## Bereich: {owner}")
        lines.append("")
        for kind in _KIND_ORDER:
            entries = [m for m in items if m.owner == owner and m.kind == kind]
            if not entries:
                continue
            lines.append(f"### {_KIND_LABEL[kind]} ({kind})")
            for m in entries:
                lines.append(f"- {m.text.replace(chr(10), ' ').strip()}")
            lines.append("")
    try:
        _md_path().write_text("\n".join(lines), encoding="utf-8")
    except OSError:
        pass


def _parse_markdown() -> list[tuple[str, str, str]]:
    """Liest memory.md -> Liste (owner, kind, text)."""
    try:
        text = _md_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    owner, kind = "shared", "fact"
    out: list[tuple[str, str, str]] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## Bereich:"):
            owner = line.split(":", 1)[1].strip() or "shared"
        elif line.startswith("### "):
            m = re.search(r"\(([a-z]+)\)\s*$", line)
            kind = m.group(1) if m and m.group(1) in _VALID_KINDS else "fact"
        elif line.startswith("- "):
            body = line[2:].strip()
            if body:
                out.append((owner, kind, body))
    return out


def import_markdown() -> dict:
    """Gleicht das Gedaechtnis an die (evtl. von Hand geaenderte) memory.md an.

    Neue Stichpunkte werden uebernommen, entfernte geloescht. Danach wird die
    Datei normalisiert neu geschrieben.
    """
    parsed = list(dict.fromkeys(_parse_markdown()))  # dedupe, Reihenfolge erhalten
    existing = {(m.owner, m.kind, m.text) for m in _read_all()}
    added = 0
    for owner, kind, body in parsed:
        if (owner, kind, body) not in existing:
            add(body, kind=kind, source="user", owner=owner)
            added += 1
    desired = set(parsed)
    kept, removed = [], 0
    for m in _read_all():
        if (m.owner, m.kind, m.text) in desired:
            kept.append(m)
        else:
            removed += 1
    if removed:
        _write_all(kept)
    export_markdown()
    return {"added": added, "removed": removed, "total": len(kept), "path": str(_md_path())}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"\w+", text.lower()) if len(t) > 2}


def _backfill_embeddings(items: list[Memory]) -> bool:
    """Berechnet fehlende Embeddings nach (fuer Altbestand) und speichert sie."""
    changed = False
    for m in items:
        if m.embedding is None:
            vec = embeddings.embed(m.text)
            if vec:
                m.embedding = vec
                changed = True
    if changed:
        _write_all(items)
    return changed


def _semantic_search(query: str, k: int, exclude_kind: Optional[str],
                     owner: Optional[str]) -> Optional[list[Memory]]:
    """Semantische Suche per Embeddings; None, wenn nicht verfuegbar."""
    if not embeddings.is_available():
        return None
    qv = embeddings.embed(query)
    if qv is None:
        return None
    items = _read_all()
    _backfill_embeddings(items)  # Altbestand nachruesten
    scored = [
        (embeddings.cosine(qv, m.embedding), m)
        for m in items
        if m.embedding and not (exclude_kind and m.kind == exclude_kind) and _visible(m, owner)
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for sim, m in scored[:k] if sim >= config.SEMANTIC_MIN_SIM]


def search(query: str, k: int = 4, exclude_kind: Optional[str] = None,
           owner: Optional[str] = None) -> list[Memory]:
    """Liefert die k relevantesten Eintraege -- semantisch, sonst lexikalisch.

    `owner` schraenkt auf den eigenen Bereich + geteilte Eintraege ein
    (Pro-Person-Trennung). None = alle Eintraege.
    """
    semantic = _semantic_search(query, k, exclude_kind, owner)
    if semantic is not None:
        return semantic

    # Fallback: lexikalische Token-Ueberlappung (ohne Embed-Modell).
    q = _tokens(query)
    if not q:
        return []
    scored: list[tuple[float, Memory]] = []
    for m in _read_all():
        if (exclude_kind and m.kind == exclude_kind) or not _visible(m, owner):
            continue
        overlap = len(q & _tokens(m.text))
        if overlap:
            scored.append((overlap / (len(_tokens(m.text)) ** 0.5 + 1), m))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:k]]
