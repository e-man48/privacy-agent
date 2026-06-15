"""Projekte -- getrennte Arbeits-Threads mit eigenem Verlauf.

Ein Projekt buendelt einen Gespraechsverlauf und einen Status. So kann ein
langes Projekt pausiert werden, waehrend man eine kurze Aufgabe in einem anderen
Projekt erledigt -- der Kontext des langen Projekts bleibt erhalten.

Das Gedaechtnis ist bewusst GETEILT (projektuebergreifend); nur der Verlauf ist
pro Projekt getrennt. Persistenz: eine JSON-Datei im Nutzer-Datenordner.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from . import config

_STATUS = ("active", "paused", "done")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new(name: str, priority: int = 0) -> dict:
    return {
        "id": uuid.uuid4().hex[:8],
        "name": name or "Neues Projekt",
        "status": "active",
        "priority": priority,
        "created": _now(),
        "updated": _now(),
        "history": [],
    }


def _load() -> dict:
    try:
        data = json.loads(config.PROJECTS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"active": None, "projects": []}
    if not data.get("projects"):
        first = _new("Allgemein")
        data = {"active": first["id"], "projects": [first]}
    if not data.get("active") or not _find(data, data["active"]):
        data["active"] = data["projects"][0]["id"]
    return data


def save(data: dict) -> None:
    config.PROJECTS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _find(data: dict, pid: str) -> Optional[dict]:
    return next((p for p in data["projects"] if p["id"] == pid), None)


# --- Oeffentliche API ---------------------------------------------------
def load() -> dict:
    """Laedt (und initialisiert) den Projektstand und speichert ggf. Defaults."""
    data = _load()
    save(data)
    return data


def get_active() -> tuple[dict, dict]:
    """Liefert (aktives_projekt, gesamtdaten). Mutationen am Projekt -> save(data)."""
    data = _load()
    project = _find(data, data["active"]) or data["projects"][0]
    return project, data


def create(name: str, priority: int = 0) -> dict:
    data = _load()
    project = _new(name, priority)
    data["projects"].append(project)
    data["active"] = project["id"]
    save(data)
    return project


def set_active(pid: str) -> bool:
    data = _load()
    if _find(data, pid) is None:
        return False
    data["active"] = pid
    save(data)
    return True


def update(pid: str, name=None, status=None, priority=None) -> Optional[dict]:
    data = _load()
    project = _find(data, pid)
    if project is None:
        return None
    if name:
        project["name"] = name
    if status in _STATUS:
        project["status"] = status
    if priority is not None:
        project["priority"] = int(priority)
    project["updated"] = _now()
    save(data)
    return project


def delete(pid: str) -> bool:
    data = _load()
    data["projects"] = [p for p in data["projects"] if p["id"] != pid]
    if data.get("active") == pid:
        data["active"] = None
    save(_load() if not data["projects"] else data)  # _load() re-initialisiert Default
    return True


def public_list() -> list[dict]:
    """Projekte ohne den (langen) Verlauf -- fuer die GUI-Liste."""
    data = load()
    out = []
    for p in data["projects"]:
        out.append({
            "id": p["id"], "name": p["name"], "status": p["status"],
            "priority": p.get("priority", 0), "updated": p["updated"],
            "messages": len(p["history"]), "active": p["id"] == data["active"],
        })
    return out
