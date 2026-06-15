"""Hintergrund-Worker -- erledigt Auftraege, ohne den Chat zu blockieren.

So kann der Agent an einer langen Aufgabe arbeiten, waehrend im Vordergrund-Chat
sofort dringende Kurzaufgaben beantwortet werden (der Vordergrund hat damit
faktisch immer Vorrang). Mehrere Hintergrund-Auftraege werden nach Prioritaet
abgearbeitet -- ein dringenderer Auftrag wird vor wartenden zuerst erledigt.

Hinweis: Ein laufender Auftrag (ein KI-Aufruf) wird nicht mitten drin
abgebrochen; die Bevorzugung greift zwischen den Auftraegen.
"""
from __future__ import annotations

import threading
import time
import uuid

from . import principals, projects, router

_jobs: dict[str, dict] = {}
_lock = threading.Lock()
_worker: threading.Thread | None = None
_running = False

# Hintergrund laeuft rein lokal (keine interaktive Cloud-Rueckfrage moeglich).
_BG_PRINCIPAL = principals.Principal("background", "Hintergrund",
                                     can_use_cloud=False, scope="local")


def _pick() -> dict | None:
    cands = [j for j in _jobs.values() if j["status"] == "queued"]
    if not cands:
        return None
    cands.sort(key=lambda j: (-j["priority"], j["created"]))
    return cands[0]


def enqueue(goal: str, project_id: str, priority: int = 0) -> str:
    jid = uuid.uuid4().hex[:8]
    with _lock:
        _jobs[jid] = {
            "id": jid, "goal": goal, "project_id": project_id,
            "priority": int(priority), "status": "queued",
            "created": time.time(), "result": "",
        }
    _ensure_worker()
    return jid


def list_jobs() -> list[dict]:
    return sorted(
        ({"id": j["id"], "goal": j["goal"], "project_id": j["project_id"],
          "priority": j["priority"], "status": j["status"],
          "result": j["result"][:200]} for j in _jobs.values()),
        key=lambda j: j["id"],
    )


def active_count() -> int:
    return sum(1 for j in _jobs.values() if j["status"] in ("queued", "running"))


def _run_one(job: dict) -> None:
    job["status"] = "running"
    data = projects.load()
    project = next((p for p in data["projects"] if p["id"] == job["project_id"]), None)
    if project is None:
        job["status"], job["result"] = "error", "Projekt nicht gefunden."
        return

    hist = list(project["history"]) + [{"role": "user", "content": job["goal"]}]
    try:
        res = router.handle_task(hist, principal=_BG_PRINCIPAL)
    except Exception as exc:  # noqa: BLE001
        job["status"], job["result"] = "error", str(exc)
        return

    if res.get("type") == "answer":
        text = res.get("text", "(keine Antwort)")
    else:
        text = "[braucht Rückfrage] " + res.get("reason", res.get("text", ""))

    # Ergebnis ins Projekt schreiben (frisch laden, um Vordergrund nicht zu ueberschreiben).
    data = projects.load()
    project = next((p for p in data["projects"] if p["id"] == job["project_id"]), None)
    if project is not None:
        project["history"].append({"role": "user", "content": "⏳ " + job["goal"]})
        project["history"].append({"role": "assistant", "content": text})
        project["updated"] = projects._now()
        projects.save(data)
    job["result"], job["status"] = text, "done"


def _loop() -> None:
    global _running
    while _running:
        with _lock:
            job = _pick()
        if job is None:
            time.sleep(1)
            continue
        _run_one(job)


def _ensure_worker() -> None:
    global _worker, _running
    if _worker is not None and _worker.is_alive():
        return
    _running = True
    _worker = threading.Thread(target=_loop, daemon=True)
    _worker.start()


def stop() -> None:
    global _running
    _running = False
