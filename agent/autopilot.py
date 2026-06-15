"""Autopilot fuer lokale Modelle.

Wenn die lokale KI bei einer Aufgabe nicht weiterkommt (niedrige Selbst-
sicherheit), versucht der Autopilot es -- sofern aktiviert -- zuerst mit einem
staerkeren LOKALEN Modell, bevor die Cloud vorgeschlagen wird. Das ist
kostenlos, bleibt auf dem Geraet (DSGVO-konform) und ist reversibel.

"Erfahrung sammeln": Schafft ein staerkeres Modell wiederholt das, woran das
aktuelle Modell scheitert, macht der Autopilot es nach genug Erfolgen autonom
zum neuen Standard (und protokolliert das nachvollziehbar).

Nur lokale Open-Source-Modelle werden autonom gewechselt -- die bezahlte Cloud
NIE ohne ausdrueckliche Einwilligung.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from . import config, local_llm, metrics

# Anzahl der Faelle, in denen ein staerkeres Modell "gewinnt", bevor es autonom
# zum neuen Standard wird.
AUTOSWITCH_WINS = 3

# Ungefaehre Parameterzahl (in Mrd.) der Standard-Variante gaengiger Modelle,
# fuer Namen OHNE Groessenangabe im Tag (z.B. 'mistral'). Bei Bedarf erweitern;
# eine explizite Groesse im Tag (z.B. ':14b') hat immer Vorrang.
_MODEL_SIZES_B: dict[str, float] = {
    "tinyllama": 1.1,
    "llama3.2": 3.0, "orca-mini": 3.0,
    "phi3": 3.8, "phi3.5": 3.8,
    "gemma3": 4.0,
    "qwen": 7.0, "qwen2": 7.0, "qwen2.5": 7.0,
    "mistral": 7.0, "llama2": 7.0, "codellama": 7.0, "deepseek-r1": 7.0,
    "llama3": 8.0, "llama3.1": 8.0,
    "gemma": 7.0, "gemma2": 9.0,
    "mistral-nemo": 12.0,
    "phi4": 14.0,
    "mistral-small": 22.0,
    "mixtral": 47.0,
    "llama3.3": 70.0,
}


def enabled() -> bool:
    # Bei gesperrtem Modell darf der Agent NICHT autonom wechseln.
    return bool(config.AUTO_LOCAL_UPGRADE) and not bool(config.MODEL_LOCKED)


def _params(model: str):
    """Parameterzahl (in Mrd.) eines Modells.

    Zuerst die explizite Groesse im Tag (z.B. 'qwen2.5:14b' -> 14.0); fehlt sie,
    die Tabelle ueber den Basisnamen (z.B. 'mistral' -> 7.0). Sonst None.
    """
    name = model.lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s*b\b", name)
    if m:
        return float(m.group(1))
    base = name.split(":")[0].split("/")[-1]
    return _MODEL_SIZES_B.get(base)


def stronger_installed_model(current: str):
    """Naechstgroesseres installiertes Modell (sanftes Upgrade) -- oder None."""
    cur = _params(current)
    best, best_p = None, None
    for name in local_llm.list_models():
        if name == current:
            continue
        p = _params(name)
        if p is None or (cur is not None and p <= cur):
            continue
        if best_p is None or p < best_p:  # das kleinste, das groesser ist
            best, best_p = name, p
    return best


# --- Erfahrungs-Speicher ------------------------------------------------
def _load_wins() -> dict:
    try:
        return json.loads(config.AUTOPILOT_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_wins(d: dict) -> None:
    config.AUTOPILOT_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _log_switch(model: str, previous) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "autoswitch_local_model",
        "detail": {"model": model},
        "previous": previous,
    }
    with open(config.OPTIMIZATION_LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _note_win(model: str) -> bool:
    """Zaehlt einen Erfolg des staerkeren Modells; wechselt ggf. autonom.

    Rueckgabe: True, wenn dadurch der Standard autonom gewechselt wurde.
    """
    wins = _load_wins()
    wins[model] = wins.get(model, 0) + 1
    switched = False
    if wins[model] >= AUTOSWITCH_WINS and model != config.LOCAL_MODEL:
        previous = config.set_override("LOCAL_MODEL", model)
        _log_switch(model, previous)
        metrics.record("autoswitch_local_model", model=model, previous=previous)
        wins[model] = 0
        switched = True
    _save_wins(wins)
    return switched


def try_upgrade(convo: list[dict], task: str, base_confidence: int):
    """Versucht die Aufgabe mit einem staerkeren lokalen Modell zu loesen.

    Rueckgabe: ein Antwort-Dict, wenn das Upgrade hilft -- sonst None
    (dann nimmt der Router den normalen Cloud-Einwilligungs-Pfad).
    """
    target = stronger_installed_model(config.LOCAL_MODEL)
    if not target:
        return None
    try:
        reply = local_llm.chat(convo, model=target)
    except local_llm.LocalLLMError:
        return None

    confidence = local_llm.self_rate(task, reply)
    metrics.record("local_upgrade_attempt", model=target,
                   confidence=confidence, base=base_confidence)
    if confidence < config.CONFIDENCE_THRESHOLD:
        return None  # auch das staerkere Modell ist unsicher

    metrics.record("local_success", confidence=confidence, model=target)
    switched = _note_win(target)
    return {
        "type": "answer",
        "text": reply,
        "source": "local",
        "confidence": confidence,
        "model": target,
        "auto_switched": switched,
    }
