"""MCP-Client -- bindet fremde Skills ueber das Model Context Protocol an.

Ein MCP-Server ist ein Subprozess, der Werkzeuge ueber JSON-RPC (zeilenweise
ueber stdin/stdout) bereitstellt. Dieser Client startet die konfigurierten
Server, listet ihre Werkzeuge und registriert sie im Werkzeug-Verzeichnis des
Agenten -- danach kann das lokale Modell sie wie eigene Werkzeuge aufrufen.

Sicherheit: MCP-Werkzeuge sind fremder Code. Sie werden standardmaessig als
`requires_consent` registriert (Einwilligung vor jedem Aufruf). Nur wenn ein
Server in der Konfiguration ausdruecklich `"trust": true` hat, entfaellt die
Rueckfrage.

Bewusst ohne Zusatz-Abhaengigkeit: ein minimaler, aber korrekter stdio-Client
mit Lese-Thread und Zeitlimits.
"""
from __future__ import annotations

import itertools
import json
import os
import shutil
import subprocess
import threading
from typing import Optional

from . import config, runtimes
from .tools.registry import TOOLS, Tool

STATUS: dict[str, dict] = {}        # servername -> {connected, tools, error}
_SERVERS: dict[str, "MCPServer"] = {}


class MCPError(RuntimeError):
    pass


class MCPServer:
    def __init__(self, name: str, command: str, args: Optional[list] = None,
                 env: Optional[dict] = None, trust: bool = False) -> None:
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.trust = trust
        self.tools: list[dict] = []
        self.proc: Optional[subprocess.Popen] = None
        self._ids = itertools.count(1)
        self._send_lock = threading.Lock()
        self._pending: dict[int, dict] = {}

    # --- Lebenszyklus ---------------------------------------------------
    def start(self) -> None:
        full_env = {**os.environ, **{k: str(v) for k, v in self.env.items()}}
        # Befehl ueber System-PATH ODER verwaltete Laufzeiten (Node/uv) aufloesen.
        resolved = runtimes.resolve(self.command) or shutil.which(self.command) or self.command
        self.proc = subprocess.Popen(
            [resolved, *self.args],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1, env=full_env,
        )
        threading.Thread(target=self._read_loop, daemon=True).start()
        self._initialize()
        self.tools = self._request("tools/list").get("tools", [])

    def stop(self) -> None:
        try:
            if self.proc:
                self.proc.terminate()
        except OSError:
            pass

    # --- Protokoll ------------------------------------------------------
    def _read_loop(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            mid = msg.get("id")
            slot = self._pending.get(mid) if mid is not None else None
            if slot is not None:
                slot["result"] = msg
                slot["event"].set()
            # Notifications / Server-Anfragen ignorieren wir bewusst.

    def _send(self, obj: dict) -> None:
        assert self.proc and self.proc.stdin
        with self._send_lock:
            self.proc.stdin.write(json.dumps(obj) + "\n")
            self.proc.stdin.flush()

    def _request(self, method: str, params: Optional[dict] = None, timeout: float = 30) -> dict:
        rid = next(self._ids)
        ev = threading.Event()
        self._pending[rid] = {"event": ev, "result": None}
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        if not ev.wait(timeout):
            self._pending.pop(rid, None)
            raise MCPError(f"Zeitueberschreitung bei '{method}'.")
        msg = self._pending.pop(rid)["result"]
        if "error" in msg:
            raise MCPError(msg["error"].get("message", "unbekannter Fehler"))
        return msg.get("result", {})

    def _initialize(self) -> None:
        self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "PrivacyAgent", "version": "0.1.0"},
        })
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        res = self._request("tools/call", {"name": tool_name, "arguments": arguments or {}},
                            timeout=120)
        parts = []
        for block in res.get("content", []):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            else:
                parts.append(f"[{block.get('type', 'inhalt')}]")
        text = "\n".join(parts).strip() or "(kein Ergebnis)"
        return ("FEHLER: " + text) if res.get("isError") else text


# --- Verwaltung ---------------------------------------------------------
def _register_tools(server: MCPServer) -> None:
    for t in server.tools:
        full = f"mcp__{server.name}__{t['name']}"
        desc = (t.get("description") or "")[:200]
        props = list(((t.get("inputSchema") or {}).get("properties") or {}).keys())
        if props:
            desc += f"  Argumente: {', '.join(props)}"

        def make(srv: MCPServer, name: str):
            def _call(**kwargs) -> str:
                return srv.call_tool(name, kwargs)
            return _call

        TOOLS[full] = Tool(full, desc, make(server, t["name"]),
                           requires_consent=not server.trust)


def start() -> None:
    """Startet alle konfigurierten MCP-Server und registriert ihre Werkzeuge."""
    stop()
    for cfg in config.load_mcp_servers():
        name = cfg.get("name")
        if not name or not cfg.get("enabled", True) or not cfg.get("command"):
            continue
        server = MCPServer(name, cfg["command"], cfg.get("args"),
                           cfg.get("env"), cfg.get("trust", False))
        try:
            server.start()
        except (OSError, MCPError, json.JSONDecodeError) as exc:
            STATUS[name] = {"connected": False, "tools": 0, "error": str(exc)}
            continue
        _SERVERS[name] = server
        _register_tools(server)
        STATUS[name] = {"connected": True, "tools": len(server.tools), "trust": server.trust}


def stop() -> None:
    for key in [k for k in TOOLS if k.startswith("mcp__")]:
        del TOOLS[key]
    for server in _SERVERS.values():
        server.stop()
    _SERVERS.clear()


def status() -> dict:
    return dict(STATUS)


def list_skills() -> list[dict]:
    skills = []
    for name, server in _SERVERS.items():
        for t in server.tools:
            skills.append({"server": name, "tool": t["name"],
                           "description": (t.get("description") or "")[:160],
                           "trust": server.trust})
    return skills
