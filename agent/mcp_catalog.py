"""Katalog beliebter MCP-Skills -- Ein-Klick-Vorlagen fuer den Assistenten/Panel.

Statt Befehlszeilen einzutippen, waehlt der Nutzer eine Vorlage und gibt nur das
Noetigste an (z.B. einen Ordner oder einen Schluessel). `build()` setzt daraus
eine fertige MCP-Server-Konfiguration zusammen (Platzhalter `{key}` werden
ersetzt).
"""
from __future__ import annotations

from typing import Optional

# Jede Vorlage: id, label, icon, description, command, args, env, params, needs.
# In args/env duerfen Platzhalter wie {path} oder {token} stehen.
TEMPLATES: list[dict] = [
    {
        "id": "dateien",
        "label": "Dateien",
        "icon": "📁",
        "description": "Lokale Dateien in einem Ordner lesen, durchsuchen und auflisten.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "{path}"],
        "env": {},
        "params": [
            {"key": "path", "label": "Welcher Ordner darf gelesen werden?",
             "kind": "path", "placeholder": "z. B. C:\\Users\\du\\Dokumente"},
        ],
        "needs": "Node.js (npx)",
        "runtime": "node",
    },
    {
        "id": "github",
        "label": "GitHub",
        "icon": "🐙",
        "description": "GitHub-Repos durchsuchen, Issues und Pull Requests lesen/erstellen.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "{token}"},
        "params": [
            {"key": "token", "label": "GitHub-Zugriffstoken (Personal Access Token)",
             "kind": "secret", "placeholder": "ghp_…"},
        ],
        "needs": "Node.js (npx)",
        "runtime": "node",
    },
    {
        "id": "websuche",
        "label": "Websuche",
        "icon": "🔎",
        "description": "Im Web suchen (über Brave Search). Benötigt einen kostenlosen API-Schlüssel.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env": {"BRAVE_API_KEY": "{key}"},
        "params": [
            {"key": "key", "label": "Brave-Search-API-Schlüssel",
             "kind": "secret", "placeholder": "von search.brave.com/api"},
        ],
        "needs": "Node.js (npx)",
        "runtime": "node",
    },
    {
        "id": "webseite",
        "label": "Webseite abrufen",
        "icon": "🌐",
        "description": "Eine Webseite holen und als Text lesen – ohne Schlüssel.",
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "env": {},
        "params": [],
        "needs": "Python (uvx)",
        "runtime": "uv",
    },
]


def public_catalog() -> list[dict]:
    """Vorlagen fuer die GUI (enthalten nur Platzhalter, keine Geheimnisse)."""
    return TEMPLATES


def _substitute(value: str, params: dict) -> str:
    for key, val in params.items():
        value = value.replace("{" + key + "}", str(val))
    return value


def build(template_id: str, params: Optional[dict] = None, trust: bool = False) -> dict:
    """Baut aus einer Vorlage + Eingaben eine MCP-Server-Konfiguration."""
    params = params or {}
    tpl = next((t for t in TEMPLATES if t["id"] == template_id), None)
    if tpl is None:
        raise ValueError(f"Unbekannte Vorlage: {template_id}")
    for p in tpl.get("params", []):
        if not str(params.get(p["key"], "")).strip():
            raise ValueError(f"Bitte ausfüllen: {p['label']}")
    args = [_substitute(a, params) for a in tpl.get("args", [])]
    env = {k: _substitute(v, params) for k, v in tpl.get("env", {}).items()}
    return {
        "name": tpl["id"],
        "command": tpl["command"],
        "args": args,
        "env": env,
        "trust": trust,
        "enabled": True,
    }
