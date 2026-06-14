"""Automatische Gedaechtnis-Vorschlaege aus dem Gespraech.

Nach jedem Austausch prueft die LOKALE KI (datenschutzfreundlich), ob im
Gespraech etwas dauerhaft Merkenswertes steckt -- typischerweise Fakten oder
Vorlieben ueber den Nutzer. Vorschlaege werden nur angezeigt; gespeichert wird
erst nach ausdruecklicher Bestaetigung (gleiche Genehmigungs-Philosophie wie
beim Cloud-Notfall und der Selbstoptimierung).

Schutz vor Nerverei:
  * Duplikate gegenueber bereits Gemerktem werden herausgefiltert.
  * In dieser Sitzung abgelehnte Vorschlaege werden nicht erneut gebracht.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

from . import config, embeddings, local_llm, memory

# In dieser Sitzung abgelehnte Vorschlaege (normalisiert), damit wir nicht
# wiederholt nachfragen.
_DISMISSED: set[str] = set()

_VALID_KINDS = {"fact", "preference"}
_DUP_THRESHOLD = 0.6  # Jaccard-Ueberlappung, ab der ein Eintrag als Duplikat gilt

# Funktionswoerter ohne Aussagewert -- sie stecken in fast jedem Eintrag
# ("Der Nutzer ...") und wuerden die Ueberlappung sonst kuenstlich aufblaehen.
_STOPWORDS = {
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem",
    "eines", "und", "oder", "mit", "ist", "sind", "war", "hat", "hatte", "haben",
    "wird", "werden", "auch", "fuer", "von", "zum", "zur", "nutzer", "user",
    "sich", "nicht", "sehr", "gerne", "immer",
}

_EXTRACT_SYSTEM = """Du extrahierst dauerhaft merkenswerte Informationen aus einem \
Gespraech -- ausschliesslich stabile Fakten oder Vorlieben ueber den Nutzer, \
die auch in spaeteren Gespraechen nuetzlich sind.

Ignoriere: aufgabenspezifische Details, Smalltalk, Einmaliges, Allgemeinwissen.

Antworte AUSSCHLIESSLICH mit einem JSON-Array. Jeder Eintrag:
  {"text": "<knappe Aussage in dritter Person>", "kind": "fact"|"preference"}
Gibt es nichts Merkenswertes, antworte mit []. Hoechstens 3 Eintraege."""


@dataclass
class Candidate:
    text: str
    kind: str


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def _tokens(text: str) -> set[str]:
    return {
        t for t in re.findall(r"\w+", text.lower())
        if len(t) > 2 and t not in _STOPWORDS
    }


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _is_duplicate(text: str, emb: Optional[list[float]] = None,
                  owner: Optional[str] = None) -> bool:
    """Duplikat-Pruefung gegen das (fuer den Bereich sichtbare) Gespeicherte.

    Pro Eintrag: gibt es beidseitig Embeddings, entscheidet die Kosinus-
    Aehnlichkeit (erkennt auch Synonyme); sonst die Token-Ueberlappung.
    """
    nt = _tokens(text)
    if not nt:
        return True
    for m in memory.visible(owner):
        if m.kind not in ("fact", "preference", "guideline"):
            continue
        if emb is not None and m.embedding:
            if embeddings.cosine(emb, m.embedding) >= config.SEMANTIC_DUP_THRESHOLD:
                return True
        elif _jaccard(nt, _tokens(m.text)) >= _DUP_THRESHOLD:
            return True
    return False


def _render(messages: list[dict], max_msgs: int) -> str:
    recent = [m for m in messages if m["role"] in ("user", "assistant")][-max_msgs:]
    rollen = {"user": "Nutzer", "assistant": "Assistent"}
    return "\n".join(f"{rollen[m['role']]}: {m['content']}" for m in recent)


def _parse(raw: str) -> list[dict]:
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _dismiss_key(text: str, owner: Optional[str]) -> str:
    return f"{owner or '*'}|{_norm(text)}"


def extract_candidates(messages: list[dict], max_msgs: int = 6, limit: int = 3,
                       owner: Optional[str] = None) -> list[Candidate]:
    """Schlaegt merkenswerte Eintraege aus den letzten Nachrichten vor.

    `owner` begrenzt Duplikat- und Ablehnungs-Pruefung auf den Bereich der
    jeweiligen Person (Pro-Person-Trennung).
    """
    if not local_llm.is_available():
        return []
    convo = _render(messages, max_msgs)
    if not convo.strip():
        return []

    try:
        raw = local_llm.chat(
            [
                {"role": "system", "content": _EXTRACT_SYSTEM},
                {"role": "user", "content": f"GESPRAECH:\n{convo}\n\nJSON-Array:"},
            ],
            temperature=0.0,
        )
    except local_llm.LocalLLMError:
        return []

    emb_on = embeddings.is_available()
    candidates: list[Candidate] = []
    accepted_tokens: list[set[str]] = []  # lexikalischer Stapel-Vergleich
    accepted_embs: list[Optional[list[float]]] = []  # semantischer Stapel-Vergleich
    for item in _parse(raw):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        kind = item.get("kind", "fact")
        if kind not in _VALID_KINDS:
            kind = "fact"
        if len(text) < 6 or len(text) > 200 or _dismiss_key(text, owner) in _DISMISSED:
            continue

        cand_emb = embeddings.embed(text) if emb_on else None
        if _is_duplicate(text, cand_emb, owner):
            continue

        # Auch gegen bereits akzeptierte Vorschlaege im selben Stapel pruefen.
        nt = _tokens(text)
        if cand_emb is not None:
            if any(e and embeddings.cosine(cand_emb, e) >= config.SEMANTIC_DUP_THRESHOLD
                   for e in accepted_embs):
                continue
        elif any(_jaccard(nt, ot) >= _DUP_THRESHOLD for ot in accepted_tokens):
            continue

        accepted_tokens.append(nt)
        accepted_embs.append(cand_emb)
        candidates.append(Candidate(text=text, kind=kind))
        if len(candidates) >= limit:
            break
    return candidates


def dismiss(text: str, owner: Optional[str] = None) -> None:
    """Merkt einen abgelehnten Vorschlag (pro Bereich), damit er nicht wiederkehrt."""
    _DISMISSED.add(_dismiss_key(text, owner))
