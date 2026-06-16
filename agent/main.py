"""Lokaler HTTP-Server, der die Tauri-GUI mit dem Agenten verbindet.

Laeuft nur auf 127.0.0.1 -- erreichbar ausschliesslich vom eigenen Geraet.
Start (Entwicklung):  python -m agent.main
Im fertigen Produkt startet die Tauri-Huelle diesen Prozess als "Sidecar".
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import (
    cloud_llm, config, connectors, consent_log, extractor, local_llm,
    local_matrix, mcp_catalog, mcp_client, memory, metrics, openrouter_auth,
    optimizer, projects, router, runtimes, scheduler, settings, tailscale_setup,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Externe Skills (MCP) im Hintergrund starten -- blockiert den Start nicht,
    # falls ein Server langsam ist.
    import threading
    threading.Thread(target=mcp_client.start, daemon=True).start()
    # Messenger-Connector (z.B. Matrix) starten, falls konfiguriert.
    await connectors.maybe_start()
    yield
    await connectors.shutdown()
    mcp_client.stop()
    scheduler.stop()


app = FastAPI(title="Privacy-Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # nur lokal erreichbar; Tauri-Origin variiert je OS
    allow_methods=["*"],
    allow_headers=["*"],
)



class ChatIn(BaseModel):
    message: str


class ConsentIn(BaseModel):
    pending_id: str
    approved: bool


class MemoryIn(BaseModel):
    text: str
    kind: str = "fact"


class OptimizeIn(BaseModel):
    proposal_id: str
    approved: bool


class DismissIn(BaseModel):
    text: str


class ModelIn(BaseModel):
    name: str


class SettingsIn(BaseModel):
    auto_local_upgrade: bool


class SetupSaveIn(BaseModel):
    settings: dict


class KeyTestIn(BaseModel):
    api_key: str


class MatrixTestIn(BaseModel):
    matrix_homeserver: str = ""
    matrix_user: str = ""
    matrix_password: str = ""
    matrix_access_token: str = ""


class MCPServerIn(BaseModel):
    name: str
    command: str
    args: list[str] = []
    env: dict = {}
    trust: bool = False


class MCPInstallIn(BaseModel):
    id: str
    params: dict = {}
    trust: bool = False


class RuntimeIn(BaseModel):
    name: str  # "node" | "uv"


class ProjectIn(BaseModel):
    name: str


class ProjectUpdateIn(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None


class JobIn(BaseModel):
    goal: str
    priority: int = 0
    project_id: Optional[str] = None


@app.get("/health")
def health() -> dict:
    return {"ok": True, "version": __import__("agent").__version__}


@app.get("/status")
def status() -> dict:
    """Zustand fuer den Einrichtungs-Assistenten und die Statusanzeige."""
    available = local_llm.is_available()
    return {
        "ollama_running": available,
        "model": config.LOCAL_MODEL,
        "model_ready": local_llm.has_model(config.LOCAL_MODEL) if available else False,
        "cloud_configured": bool(config.ANTHROPIC_API_KEY),
        "connector": connectors.status(),
    }


@app.get("/log")
def log() -> dict:
    return {"entries": consent_log.read_log()}


@app.post("/chat")
def chat(body: ChatIn) -> dict:
    project, data = projects.get_active()
    project["history"].append({"role": "user", "content": body.message})
    result = router.handle_task(project["history"])
    if result["type"] == "answer":
        project["history"].append({"role": "assistant", "content": result["text"]})
    project["updated"] = projects._now()
    projects.save(data)
    return result


@app.post("/consent")
def consent(body: ConsentIn) -> dict:
    result = router.resolve_consent(body.pending_id, body.approved)
    if result.get("type") == "answer":
        project, data = projects.get_active()
        project["history"].append({"role": "assistant", "content": result["text"]})
        projects.save(data)
    return result


# --- Projekte (getrennte Arbeits-Threads) -------------------------------
@app.get("/projects")
def projects_list() -> dict:
    return {"projects": projects.public_list()}


@app.post("/projects")
def projects_create(body: ProjectIn) -> dict:
    p = projects.create(body.name)
    return {"ok": True, "id": p["id"]}


@app.post("/projects/{pid}/activate")
def projects_activate(pid: str) -> dict:
    return {"ok": projects.set_active(pid)}


@app.get("/projects/{pid}/messages")
def projects_messages(pid: str) -> dict:
    data = projects.load()
    p = next((x for x in data["projects"] if x["id"] == pid), None)
    return {"messages": p["history"] if p else []}


@app.patch("/projects/{pid}")
def projects_update(pid: str, body: ProjectUpdateIn) -> dict:
    p = projects.update(pid, name=body.name, status=body.status)
    return {"ok": p is not None}


@app.delete("/projects/{pid}")
def projects_delete(pid: str) -> dict:
    return {"ok": projects.delete(pid)}


# --- Hintergrund-Auftraege (Stufe B) ------------------------------------
@app.post("/jobs")
def jobs_create(body: JobIn) -> dict:
    """Startet einen Auftrag im Hintergrund (Chat bleibt frei nutzbar).

    Beginnt der Auftrag mit "dringend" (o.ae.), bekommt er Vorrang.
    """
    pid = body.project_id or projects.get_active()[0]["id"]
    urgency, goal = scheduler.parse_urgency(body.goal)
    priority = max(body.priority, urgency)
    jid = scheduler.enqueue(goal, pid, priority)
    return {"ok": True, "id": jid, "urgent": priority >= scheduler.URGENT_PRIORITY}


@app.get("/jobs")
def jobs_list() -> dict:
    return {"jobs": scheduler.list_jobs(), "active": scheduler.active_count()}


# --- Tailscale (Ein-Klick-Einrichtung) ----------------------------------
@app.get("/tailscale")
def tailscale_status() -> dict:
    return tailscale_setup.status()


@app.post("/tailscale/install")
def tailscale_install() -> dict:
    log: list[str] = []
    ok = tailscale_setup.install(log.append)
    return {"ok": ok, "log": log, "status": tailscale_setup.status()}


@app.post("/tailscale/login")
def tailscale_login() -> dict:
    ok, message = tailscale_setup.login()
    return {"ok": ok, "message": message}


# --- Lokaler Matrix-Server (Docker, optional) ---------------------------
class LocalMatrixIn(BaseModel):
    server_name: str = "localhost"


@app.get("/local-matrix")
def local_matrix_status() -> dict:
    return local_matrix.status()


@app.post("/local-matrix/start")
def local_matrix_start(body: LocalMatrixIn) -> dict:
    log: list[str] = []
    ok = local_matrix.start(body.server_name, log.append)
    return {"ok": ok, "log": log, "status": local_matrix.status()}


@app.post("/local-matrix/stop")
def local_matrix_stop() -> dict:
    return {"ok": local_matrix.stop()}


# --- Gedaechtnis --------------------------------------------------------
def _mem_public(m) -> dict:
    """Eintrag ohne den (grossen) Embedding-Vektor fuer die GUI."""
    d = m.__dict__.copy()
    d.pop("embedding", None)
    return d


@app.get("/memory")
def memory_list() -> dict:
    return {"items": [_mem_public(m) for m in memory.all()]}


@app.post("/memory")
def memory_add(body: MemoryIn) -> dict:
    mem = memory.add(body.text, kind=body.kind, source="user", owner="local")
    return {"ok": True, "item": _mem_public(mem)}


@app.delete("/memory/{mem_id}")
def memory_delete(mem_id: str) -> dict:
    return {"ok": memory.forget(mem_id)}


@app.post("/memory/suggest")
def memory_suggest() -> dict:
    """Automatische Vorschlaege aus dem aktiven Projekt (lokal erzeugt)."""
    project, _ = projects.get_active()
    cands = extractor.extract_candidates(project["history"], owner="local")
    return {"candidates": [c.__dict__ for c in cands]}


@app.post("/memory/dismiss")
def memory_dismiss(body: DismissIn) -> dict:
    extractor.dismiss(body.text, owner="local")
    return {"ok": True}


# --- Selbstoptimierung --------------------------------------------------
@app.get("/optimize/suggestions")
def optimize_suggestions() -> dict:
    return {
        "metrics": metrics.summary(),
        "proposals": [p.__dict__ for p in optimizer.analyze()],
    }


@app.post("/optimize/apply")
def optimize_apply(body: OptimizeIn) -> dict:
    return optimizer.apply(body.proposal_id, body.approved)


# --- Lokale Modelle & Autopilot -----------------------------------------
@app.get("/models")
def models_list() -> dict:
    return {
        "current": config.LOCAL_MODEL,
        "installed": local_llm.list_models(),
        "auto_local_upgrade": config.AUTO_LOCAL_UPGRADE,
    }


@app.post("/model/set")
def model_set(body: ModelIn) -> dict:
    """Wechselt das aktive lokale Modell sofort im laufenden Prozess."""
    previous = config.set_override("LOCAL_MODEL", body.name)
    return {"ok": True, "current": config.LOCAL_MODEL, "previous": previous}


@app.post("/model/pull")
def model_pull(body: ModelIn) -> dict:
    """Laedt ein neues Modell im Hintergrund (ollama pull)."""
    import subprocess
    import threading

    def worker() -> None:
        try:
            from ._proc import no_window
            subprocess.run(["ollama", "pull", body.name], check=True, **no_window())
        except (subprocess.CalledProcessError, OSError):
            pass

    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True, "message": f"Download von '{body.name}' gestartet."}


@app.post("/settings")
def settings_set(body: SettingsIn) -> dict:
    config.set_override("AUTO_LOCAL_UPGRADE", body.auto_local_upgrade)
    return {"ok": True, "auto_local_upgrade": config.AUTO_LOCAL_UPGRADE}


# --- Externe Skills (MCP) -----------------------------------------------
@app.get("/mcp")
def mcp_list() -> dict:
    return {
        "servers": config.load_mcp_servers(),
        "status": mcp_client.status(),
        "skills": mcp_client.list_skills(),
    }


@app.post("/mcp/servers")
def mcp_add(body: MCPServerIn) -> dict:
    servers = [s for s in config.load_mcp_servers() if s.get("name") != body.name]
    servers.append(body.model_dump())
    config.save_mcp_servers(servers)
    mcp_client.start()  # neu verbinden
    return {"ok": True, "status": mcp_client.status()}


@app.delete("/mcp/servers/{name}")
def mcp_remove(name: str) -> dict:
    servers = [s for s in config.load_mcp_servers() if s.get("name") != name]
    config.save_mcp_servers(servers)
    mcp_client.start()
    return {"ok": True, "status": mcp_client.status()}


@app.post("/mcp/reload")
def mcp_reload() -> dict:
    mcp_client.start()
    return {"ok": True, "status": mcp_client.status()}


@app.get("/runtimes")
def runtimes_status() -> dict:
    return runtimes.status()


@app.post("/runtimes/install")
def runtimes_install(body: RuntimeIn) -> dict:
    """Richtet eine Laufzeit (Node.js oder uv) automatisch ein."""
    log: list[str] = []
    try:
        runtimes.ensure(body.name, log.append)
    except Exception as exc:  # Download-/Entpack-/Netzfehler
        return {"ok": False, "message": str(exc), "log": log}
    return {"ok": True, "status": runtimes.status(), "log": log}


@app.get("/mcp/catalog")
def mcp_catalog_list() -> dict:
    return {"templates": mcp_catalog.public_catalog()}


@app.post("/mcp/install")
def mcp_install(body: MCPInstallIn) -> dict:
    """Installiert einen Skill aus einer Ein-Klick-Vorlage."""
    try:
        cfg = mcp_catalog.build(body.id, body.params, body.trust)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    servers = [s for s in config.load_mcp_servers() if s.get("name") != cfg["name"]]
    servers.append(cfg)
    config.save_mcp_servers(servers)
    mcp_client.start()
    return {"ok": True, "status": mcp_client.status()}


# --- Einrichtungs-Assistent (Erststart) ---------------------------------
@app.get("/setup/state")
def setup_state() -> dict:
    """Alles, was der Assistent braucht, um den richtigen Schritt zu zeigen."""
    ollama = local_llm.is_available()
    saved = settings.public()
    return {
        "onboarded": bool(saved.get("onboarded")),
        "ollama_running": ollama,
        "model": config.LOCAL_MODEL,
        "model_ready": local_llm.has_model(config.LOCAL_MODEL) if ollama else False,
        "installed_models": local_llm.list_models() if ollama else [],
        "cloud_configured": bool(config.ANTHROPIC_API_KEY),
        "connector": connectors.status(),
        "settings": saved,
    }


@app.post("/setup/cloud-test")
def setup_cloud_test(body: KeyTestIn) -> dict:
    ok, message = cloud_llm.test_key(body.api_key)
    return {"ok": ok, "message": message}


@app.post("/setup/matrix-test")
async def setup_matrix_test(body: MatrixTestIn) -> dict:
    from .connectors.matrix_connector import test_connection

    ok, message = await test_connection(
        body.matrix_homeserver, body.matrix_user,
        body.matrix_password, body.matrix_access_token,
    )
    return {"ok": ok, "message": message}


@app.post("/oauth/openrouter/start")
def openrouter_start() -> dict:
    """Oeffnet die OpenRouter-Anmeldung im Browser (OAuth-Login)."""
    openrouter_auth.start()
    return {"ok": True}


@app.get("/oauth/openrouter/callback")
def openrouter_callback(code: str = ""):
    """Wird von OpenRouter nach der Anmeldung aufgerufen; holt den Schluessel."""
    from fastapi.responses import HTMLResponse

    page = "<html><body style='font-family:sans-serif;text-align:center;padding:3rem'>{}</body></html>"
    if not code:
        return HTMLResponse(page.format("<h2>Kein Code erhalten.</h2>"))
    try:
        key = openrouter_auth.exchange(code)
    except Exception as exc:  # noqa: BLE001
        return HTMLResponse(page.format(f"<h2>Anmeldung fehlgeschlagen:</h2><p>{exc}</p>"))
    if not key:
        return HTMLResponse(page.format("<h2>Kein Schlüssel erhalten.</h2>"))
    settings.save({
        "openrouter_api_key": key,
        "cloud_provider": "openrouter",
        "cloud_mode": "api",
    })
    return HTMLResponse(page.format(
        "<h2>✅ Mit OpenRouter verbunden.</h2>"
        "<p>Du kannst dieses Fenster schließen und zum Privacy-Agent zurückkehren.</p>"
    ))


@app.post("/setup/save")
async def setup_save(body: SetupSaveIn) -> dict:
    """Speichert die Assistenten-Eingaben und macht sie sofort aktiv."""
    saved = settings.save(body.settings)
    # Falls Messenger-Einstellungen dabei waren: Connector neu starten.
    if any(k == "connector" or k.startswith("matrix_") for k in body.settings):
        await connectors.restart()
    return {"ok": True, "settings": settings.public(), "onboarded": bool(saved.get("onboarded"))}


def run(host: Optional[str] = None, port: Optional[int] = None) -> None:
    uvicorn.run(app, host=host or config.HOST, port=port or config.PORT, log_level="info")


if __name__ == "__main__":
    run()
