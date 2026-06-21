"""Leichte Nutzungs-Telemetrie -- ausschliesslich lokal.

Erfasst, wie der Agent arbeitet (lokal geloest, eskaliert, abgelehnt, ...),
damit der Optimierer datengestuetzte Verbesserungsvorschlaege machen kann.
Es werden KEINE Inhalte gespeichert, nur Ereignis-Typen und Kennzahlen.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import config


def record(event: str, **fields) -> None:
    """Haengt ein Ereignis an. Schlaegt nie auf den Hauptablauf durch."""
    try:
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
        with open(config.METRICS_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _read(limit: int) -> list[dict]:
    try:
        with open(config.METRICS_PATH, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        return []
    return [json.loads(line) for line in lines[-limit:] if line.strip()]


def tool_usage(limit: int = 500) -> dict:
    """Zaehlt, wie oft welches Werkzeug/welcher Skill tatsaechlich genutzt wurde."""
    usage: dict[str, int] = {}
    for e in _read(limit):
        if e.get("event") == "tool_used" and e.get("tool"):
            usage[e["tool"]] = usage.get(e["tool"], 0) + 1
    return usage


def summary(limit: int = 300) -> dict:
    """Aggregierte Kennzahlen ueber die letzten Ereignisse."""
    events = _read(limit)
    counts: dict[str, int] = {}
    confidences: list[int] = []
    for e in events:
        counts[e["event"]] = counts.get(e["event"], 0) + 1
        if e["event"] == "local_success" and isinstance(e.get("confidence"), int):
            confidences.append(e["confidence"])

    local = counts.get("local_success", 0)
    escalated = counts.get("escalation_requested", 0)
    denied = counts.get("consent_denied", 0)
    total_tasks = local + escalated

    return {
        "samples": len(events),
        "total_tasks": total_tasks,
        "local_success": local,
        "escalation_requested": escalated,
        "consent_denied": denied,
        "cloud_answer": counts.get("cloud_answer", 0),
        "escalation_rate": round(escalated / total_tasks, 3) if total_tasks else 0.0,
        "deny_rate": round(denied / escalated, 3) if escalated else 0.0,
        "avg_confidence": round(sum(confidences) / len(confidences), 2) if confidences else None,
    }
