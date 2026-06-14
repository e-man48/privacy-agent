"""DSGVO-Protokoll fuer Cloud-Aufrufe.

Jede Eskalation in die Cloud -- und jede Einwilligung oder Ablehnung -- wird
als eine Zeile JSON festgehalten. So kann der Nutzer jederzeit nachweisen,
welche Daten wann das Geraet verlassen haben (Transparenz, Rechenschaftspflicht
nach Art. 5 DSGVO).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal

from . import config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(
    event: Literal["consent_requested", "consent_granted", "consent_denied", "cloud_call"],
    *,
    task: str,
    data_sent: str = "",
    model: str = "",
) -> None:
    """Schreibt einen Protokolleintrag (anhaengend, nie ueberschreibend)."""
    entry = {
        "timestamp": _now(),
        "event": event,
        "task": task,
        "data_sent": data_sent,
        "model": model,
    }
    with open(config.CONSENT_LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_log(limit: int = 200) -> list[dict]:
    """Liest die letzten Protokolleintraege (fuer eine Anzeige in der GUI)."""
    try:
        with open(config.CONSENT_LOG_PATH, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        return []
    return [json.loads(line) for line in lines[-limit:] if line.strip()]
