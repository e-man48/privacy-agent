"""Gemeinsame Gespraechs-Pipeline fuer alle Messenger-Connectoren.

Verbindet eingehende Nachrichten mit derselben Agenten-"Brain"-Logik wie die
GUI (agent.router) -- inklusive der Einwilligungs-Rueckfrage. Da ein Messenger
keinen Dialog-Button hat, wird die Rueckfrage als Text gestellt und mit
"JA"/"NEIN" beantwortet.

Pro Kanal (z.B. Matrix-Raum) werden Verlauf und ein evtl. offener Einwilligungs-
Vorgang getrennt gehalten.
"""
from __future__ import annotations

from .. import extractor, memory, router

_YES = {"ja", "j", "yes", "y", "ok", "okay", "klar", "jo", "👍"}
_NO = {"nein", "n", "no", "nope", "stop", "abbrechen", "👎"}

# Antworten auf einen Merk-Vorschlag.
_MEM_YES = {"merken", "merk", "ja", "speichern", "speicher", "👍"}
_MEM_NO = {"nein", "nö", "vergiss", "verwerfen", "nicht", "👎"}


def _is_yes(text: str) -> bool:
    return text.strip().lower() in _YES


def _source_tag(res: dict) -> str:
    if res.get("source") == "cloud":
        return "\n\n— ☁️ via Cloud (Claude)"
    model = f" ({res['model']})" if res.get("model") else ""
    conf = f", Konfidenz {res['confidence']}/10" if res.get("confidence") is not None else ""
    return f"\n\n— 🔒 lokal{model}{conf}"


class Conversations:
    """Haelt Verlauf und offene Einwilligungen je Kanal."""

    def __init__(self) -> None:
        self._history: dict[str, list[dict]] = {}
        self._pending: dict[str, str] = {}  # channel_id -> pending_id (Cloud)
        self._pending_memory: dict[str, list] = {}  # channel_id -> Kandidaten

    def process(self, principal, text: str) -> str:
        """Verarbeitet eine Nachricht einer Person und liefert die Antwort.

        Verlauf und offene Rueckfragen werden PRO Person (principal.id) gefuehrt
        -- so bleiben mehrere Nutzer sauber getrennt, auch im selben Raum.
        """
        cid = principal.id

        # 1) Offene Cloud-Rueckfrage? -> JA/NEIN.
        if cid in self._pending:
            pid = self._pending.pop(cid)
            res = router.resolve_consent(pid, _is_yes(text))
            return self._format(principal, res)

        # 2) Offener Merk-Vorschlag? -> MERKEN/NEIN (sonst verfaellt er).
        if cid in self._pending_memory:
            handled = self._resolve_memory(principal, text)
            if handled is not None:
                return handled
            # weder Zustimmung noch Ablehnung -> als neue Nachricht weiter.

        # 3) Normale Aufgabe.
        hist = self._history.setdefault(cid, [])
        hist.append({"role": "user", "content": text})
        res = router.handle_task(hist, principal=principal)
        return self._format(principal, res)

    def _resolve_memory(self, principal, text: str):
        """Behandelt die Antwort auf einen Merk-Vorschlag; None = keine Antwort."""
        cid = principal.id
        low = text.strip().lower()
        if low in _MEM_YES:
            cands = self._pending_memory.pop(cid)
            for c in cands:
                memory.add(c.text, kind=c.kind, source="auto", owner=principal.scope)
            return "✅ Gemerkt."
        if low in _MEM_NO:
            cands = self._pending_memory.pop(cid)
            for c in cands:
                extractor.dismiss(c.text, principal.scope)
            return "Ok, ich merke es mir nicht."
        # Etwas anderes -> Vorschlag verfaellt (nicht erneut fragen).
        for c in self._pending_memory.pop(cid):
            extractor.dismiss(c.text, principal.scope)
        return None

    def _format(self, principal, res: dict) -> str:
        cid = principal.id
        kind = res.get("type")
        if kind == "answer":
            self._history.setdefault(cid, []).append(
                {"role": "assistant", "content": res["text"]}
            )
            return res["text"] + _source_tag(res) + self._maybe_suggest(principal)
        if kind == "consent_required":
            self._pending[cid] = res["pending_id"]
            preview = res.get("data_preview", "")
            return (
                f"⚠️ {res['reason']}\n\n"
                f"Betroffene Daten: {preview}\n\n"
                f"Antworte mit *JA* (senden) oder *NEIN* (lokal bleiben)."
            )
        return "⚠️ " + res.get("text", "Unbekannter Fehler.")

    def _maybe_suggest(self, principal) -> str:
        """Prueft, ob etwas Merkenswertes im Gespraech steckt (pro Person)."""
        cid = principal.id
        cands = extractor.extract_candidates(
            self._history[cid], owner=principal.scope, limit=2
        )
        if not cands:
            return ""
        self._pending_memory[cid] = cands
        items = " und ".join(f"„{c.text}“" for c in cands)
        return f"\n\n💡 Soll ich mir merken: {items}? Antworte mit *MERKEN* oder *NEIN*."
