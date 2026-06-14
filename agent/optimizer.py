"""Selbstoptimierung -- datengestuetzt, eingegrenzt und reversibel.

WICHTIG -- Sicherheitsgrenzen:
  * Der Agent aendert NIEMALS eigenen Quellcode.
  * Vorschlaege betreffen ausschliesslich eine Whitelist umkehrbarer Stellen:
      - getunte Parameter (config._TUNABLE)
      - gelernte Betriebsregeln (Gedaechtnis-Eintraege, kind="guideline")
      - Gedaechtnis-Eintraege (Fakten/Vorlieben)
  * Jeder Vorschlag wird begruendet (aus echten Nutzungsdaten) und erst nach
    ausdruecklicher Genehmigung angewandt.
  * Jede angewandte Aenderung wird mit ihrem vorherigen Wert protokolliert
    (optimization_log.jsonl) -- dadurch nachvollziehbar und rueckgaengig machbar.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from . import config, memory, metrics

# Mindestzahl beobachteter Aufgaben, bevor ueberhaupt optimiert wird.
MIN_SAMPLES = 5

_PENDING: dict[str, "Proposal"] = {}


@dataclass
class Proposal:
    id: str
    kind: str  # "set_config" | "add_guideline" | "add_memory" | "pull_model"
    title: str
    rationale: str
    change: dict[str, Any] = field(default_factory=dict)
    risk: str = "gering"


def _log(action: str, detail: dict, previous: Any = None) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "detail": detail,
        "previous": previous,
    }
    with open(config.OPTIMIZATION_LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _bigger_model(model: str) -> Optional[str]:
    ladder = ["qwen2.5:3b", "qwen2.5:7b", "qwen2.5:14b", "qwen2.5:32b"]
    base = model.split(":")[0]
    sized = [m for m in ladder if m.split(":")[0] == base]
    try:
        idx = ladder.index(model)
    except ValueError:
        return None
    return ladder[idx + 1] if idx + 1 < len(ladder) else None


def analyze() -> list[Proposal]:
    """Leitet aus den Nutzungsdaten Verbesserungsvorschlaege ab."""
    _PENDING.clear()
    s = metrics.summary()
    proposals: list[Proposal] = []

    if s["total_tasks"] < MIN_SAMPLES:
        return proposals  # zu wenig Daten fuer belastbare Vorschlaege

    esc = s["escalation_rate"]
    deny = s["deny_rate"]
    avg = s["avg_confidence"]

    # Regel A: Viel eskaliert, aber Nutzer lehnt Cloud meist ab
    #          -> Schwelle senken, damit lokal haeufiger probiert wird.
    if esc >= 0.4 and deny >= 0.5 and config.CONFIDENCE_THRESHOLD > 2:
        new = config.CONFIDENCE_THRESHOLD - 1
        proposals.append(Proposal(
            id="", kind="set_config",
            title=f"Eskalations-Schwelle auf {new} senken",
            rationale=(
                f"Eskalationsrate {esc:.0%}, aber {deny:.0%} der Cloud-Anfragen "
                f"hast du abgelehnt. Eine niedrigere Schwelle versucht mehr lokal."
            ),
            change={"key": "CONFIDENCE_THRESHOLD", "value": new},
        ))

    # Regel B: Viel eskaliert, Cloud wird akzeptiert -> staerkeres lokales Modell.
    if esc >= 0.5 and deny < 0.5:
        bigger = _bigger_model(config.LOCAL_MODEL)
        if bigger:
            proposals.append(Proposal(
                id="", kind="pull_model",
                title=f"Staerkeres lokales Modell '{bigger}' laden",
                rationale=(
                    f"Eskalationsrate {esc:.0%} -- das lokale Modell "
                    f"'{config.LOCAL_MODEL}' reicht oft nicht. Ein groesseres "
                    f"Modell koennte mehr lokal (datenschutzfreundlich) loesen."
                ),
                change={"model": bigger},
                risk="mittel (Download noetig, mehr RAM-Bedarf)",
            ))

    # Regel C: Lokale Antworten sehr sicher -> Qualitaetsschwelle anheben.
    if avg is not None and avg >= 8.5 and esc < 0.1 and config.CONFIDENCE_THRESHOLD < 8:
        new = config.CONFIDENCE_THRESHOLD + 1
        proposals.append(Proposal(
            id="", kind="set_config",
            title=f"Qualitaetsschwelle auf {new} anheben",
            rationale=(
                f"Durchschnittliche Selbstsicherheit {avg}/10 bei nur {esc:.0%} "
                f"Eskalationen -- die Schwelle kann strenger werden."
            ),
            change={"key": "CONFIDENCE_THRESHOLD", "value": new},
        ))

    # Regel D: Nutzer bevorzugt klar lokal -> als Betriebsregel verankern.
    has_local_rule = any("lokal" in g.text.lower() for g in memory.by_kind("guideline"))
    if deny >= 0.6 and not has_local_rule:
        text = (
            "Der Nutzer bevorzugt datensparsame, lokale Loesungen. "
            "Eskaliere nur, wenn es wirklich noetig ist, und nutze zuerst die Werkzeuge."
        )
        proposals.append(Proposal(
            id="", kind="add_guideline",
            title="Betriebsregel: zurueckhaltend eskalieren",
            rationale=f"Du hast {deny:.0%} der Cloud-Anfragen abgelehnt.",
            change={"text": text},
        ))

    # IDs vergeben und zwischenspeichern.
    for p in proposals:
        p.id = uuid.uuid4().hex[:10]
        _PENDING[p.id] = p
    return proposals


def apply(proposal_id: str, approved: bool) -> dict:
    """Wendet einen Vorschlag NACH Genehmigung an (oder verwirft ihn)."""
    p = _PENDING.pop(proposal_id, None)
    if p is None:
        return {"ok": False, "message": "Unbekannter oder abgelaufener Vorschlag."}

    if not approved:
        _log("rejected", {"title": p.title, "kind": p.kind})
        return {"ok": True, "message": f"Verworfen: {p.title}"}

    if p.kind == "set_config":
        key, value = p.change["key"], p.change["value"]
        previous = config.set_override(key, value)
        _log("set_config", {"key": key, "value": value}, previous=previous)
        return {"ok": True, "message": f"{key} = {value} (vorher {previous})"}

    if p.kind == "add_guideline":
        mem = memory.add(p.change["text"], kind="guideline", source="optimizer", owner="shared")
        _log("add_guideline", {"id": mem.id, "text": mem.text})
        return {"ok": True, "message": "Neue Betriebsregel gespeichert."}

    if p.kind == "add_memory":
        mem = memory.add(p.change["text"], kind=p.change.get("memkind", "fact"),
                         source="optimizer", owner="shared")
        _log("add_memory", {"id": mem.id, "text": mem.text})
        return {"ok": True, "message": "Gedaechtnis-Eintrag gespeichert."}

    if p.kind == "pull_model":
        return _apply_pull_model(p)

    return {"ok": False, "message": f"Unbekannte Vorschlagsart: {p.kind}"}


def _apply_pull_model(p: Proposal) -> dict:
    """Laedt ein groesseres Modell im Hintergrund und stellt danach um."""
    import threading
    import subprocess

    model = p.change["model"]

    def worker() -> None:
        try:
            subprocess.run(["ollama", "pull", model], check=True)
            previous = config.set_override("LOCAL_MODEL", model)
            _log("pull_model", {"model": model}, previous=previous)
        except (subprocess.CalledProcessError, OSError) as exc:
            _log("pull_model_failed", {"model": model, "error": str(exc)})

    threading.Thread(target=worker, daemon=True).start()
    return {
        "ok": True,
        "message": f"Download von '{model}' laeuft im Hintergrund. "
                   "Nach Abschluss wird automatisch umgestellt.",
    }
