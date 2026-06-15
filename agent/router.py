"""Router: entscheidet zwischen lokaler Loesung und Cloud-Eskalation.

Ablauf (siehe README, Abschnitt "Eskalations-Schleife"):

  1. Lokales Modell versucht die Aufgabe -- mit Zugriff auf lokale Werkzeuge.
  2. Will das Modell ein Werkzeug nutzen, das das Geraet verlaesst (z.B. Web-
     Suche), wird angehalten und eine Einwilligung angefordert.
  3. Ist die lokale Antwort zu unsicher (Selbstbewertung < Schwelle) oder
     schlaegt fehl, wird eine Cloud-Eskalation angefordert.
  4. Cloud wird NUR nach ausdruecklicher Einwilligung aufgerufen; jeder Schritt
     landet im DSGVO-Protokoll.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import uuid
import webbrowser
from dataclasses import dataclass, field
from typing import Any, Optional

from . import autopilot, cloud_llm, config, consent_log, local_llm, memory, metrics, principals

_PROVIDER_LABEL = {"claude": "Claude", "chatgpt": "ChatGPT", "gemini": "Gemini"}


def _provider_label(provider: str) -> str:
    return _PROVIDER_LABEL.get(provider, "die KI")


def _browser_url(provider: str, prompt: str) -> str:
    """Web-Chat-URL des Abos -- mit vorbefuellter Frage, wo unterstuetzt."""
    q = urllib.parse.quote(prompt)
    if provider == "chatgpt":
        return f"https://chatgpt.com/?q={q}"
    if provider == "gemini":
        return "https://gemini.google.com/app"
    return f"https://claude.ai/new?q={q}"
from .tools import TOOLS, run_tool, tool_descriptions

_BASE_PROMPT = """Du bist ein eigenstaendiger, hilfreicher Assistent, der so weit \
wie moeglich lokal und datenschutzfreundlich arbeitet.

Dir stehen folgende Werkzeuge zur Verfuegung:
{tools}

Wenn du ein Werkzeug brauchst, antworte AUSSCHLIESSLICH mit einem JSON-Objekt:
  {{"tool": "name", "args": {{...}}}}
Wenn du die Aufgabe final beantworten kannst, antworte mit normalem Text \
(kein JSON). Nutze Werkzeuge nur, wenn noetig."""


def build_system_prompt(task: str, owner: Optional[str] = None) -> str:
    """Baut den System-Prompt dynamisch -- inkl. gelerntem Gedaechtnis.

    Betriebsregeln (kind="guideline") fliessen immer ein; weitere Eintraege
    nur, wenn sie zur aktuellen Aufgabe passen (lexikalischer Abruf).
    `owner` begrenzt das Gedaechtnis auf den eigenen Bereich + Geteiltes.
    """
    parts = [_BASE_PROMPT.format(tools=tool_descriptions())]

    guidelines = memory.by_kind("guideline", owner=owner)
    if guidelines:
        parts.append(
            "Beachte diese gelernten Betriebsregeln:\n"
            + "\n".join(f"- {g.text}" for g in guidelines)
        )

    relevant = memory.search(task, k=4, exclude_kind="guideline", owner=owner)
    if relevant:
        parts.append(
            "Was du dir gemerkt hast (nur nutzen, wenn relevant):\n"
            + "\n".join(f"- {m.text}" for m in relevant)
        )

    return "\n\n".join(parts)

# Zwischenspeicher fuer Aktionen, die auf eine Einwilligung warten.
_PENDING: dict[str, "PendingAction"] = {}


@dataclass
class PendingAction:
    kind: str  # "cloud" oder "tool"
    reason: str
    data_preview: str
    messages: list[dict]
    payload: dict[str, Any] = field(default_factory=dict)


def _answer(text: str, source: str, confidence: Optional[int] = None) -> dict:
    return {"type": "answer", "text": text, "source": source, "confidence": confidence}


def _consent(action: PendingAction) -> dict:
    pid = uuid.uuid4().hex
    _PENDING[pid] = action
    consent_log.log_event(
        "consent_requested",
        task=_last_user(action.messages),
        data_sent=action.data_preview,
        model=config.CLOUD_MODEL if action.kind == "cloud" else "",
    )
    return {
        "type": "consent_required",
        "pending_id": pid,
        "kind": action.kind,
        "reason": action.reason,
        "data_preview": action.data_preview,
    }


def _last_user(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m["role"] == "user":
            return m["content"]
    return ""


def _try_parse_tool_call(text: str) -> Optional[dict]:
    """Erkennt einen Werkzeug-Aufruf im Modell-Output (tolerant)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if isinstance(obj, dict) and "tool" in obj:
        return obj
    return None


def _cloud_or_block(principal, reason: str, preview: str, messages: list[dict]) -> dict:
    """Behandelt die Eskalation je nach Notfall-Modus und Berechtigung."""
    if not principal.can_use_cloud or config.CLOUD_MODE == "off":
        metrics.record("cloud_blocked", user=principal.id)
        return _answer(
            "Ich komme hier lokal nicht sicher weiter und darf/soll die "
            "Notfall-Hilfe nicht nutzen. Du kannst sie im 🧠-Menü aktivieren – "
            "oder eine berechtigte Person fragen.",
            source="local",
        )

    if config.CLOUD_MODE == "browser":
        # Abo-Hilfe im Browser: nur sinnvoll, wenn der Mensch am PC ist (GUI).
        if principal.id != "local":
            return _answer(
                "Ich komme lokal nicht weiter. Die Abo-Hilfe im Browser geht nur "
                "direkt am PC, nicht aus der Ferne.",
                source="local",
            )
        label = _provider_label(config.BROWSER_PROVIDER)
        return _consent(
            PendingAction(
                kind="browser",
                reason=(f"Lokal unsicher. Soll ich {label} im Browser öffnen? "
                        "Die Frage kommt in die Zwischenablage – du nutzt dann dein Abo."),
                data_preview=preview,
                messages=messages,
                payload={"prompt": preview},
            )
        )

    # CLOUD_MODE == "api"
    return _consent(
        PendingAction(kind="cloud", reason=reason, data_preview=preview, messages=messages)
    )


def handle_task(messages: list[dict], principal=None, max_tool_steps: int = 4) -> dict:
    """Verarbeitet eine Aufgabe lokal und eskaliert bei Bedarf.

    `principal` bestimmt Gedaechtnis-Bereich und Cloud-Berechtigung
    (Pro-Person-Trennung). Ohne Angabe gilt der lokale GUI-Nutzer.
    """
    principal = principal or principals.gui()

    if not local_llm.is_available():
        # Lokale KI laeuft nicht -> ehrliche Eskalation an den Nutzer.
        metrics.record("escalation_requested", reason="unavailable")
        return _cloud_or_block(
            principal,
            "Die lokale KI ist nicht erreichbar (Ollama nicht gestartet?).",
            _last_user(messages),
            messages,
        )

    convo = [{"role": "system",
              "content": build_system_prompt(_last_user(messages), principal.scope)}] + messages

    for _ in range(max_tool_steps):
        try:
            reply = local_llm.chat(convo)
        except local_llm.LocalLLMError as exc:
            metrics.record("escalation_requested", reason="error")
            return _cloud_or_block(
                principal, f"Lokale KI-Fehler: {exc}", _last_user(messages), messages
            )

        call = _try_parse_tool_call(reply)
        if call is None:
            # Finale Antwort -> Konfidenz pruefen.
            task = _last_user(messages)
            confidence = local_llm.self_rate(task, reply)
            if confidence < config.CONFIDENCE_THRESHOLD:
                # Autopilot: zuerst ein staerkeres LOKALES Modell versuchen,
                # bevor die (bezahlte) Cloud ins Spiel kommt.
                if autopilot.enabled():
                    upgraded = autopilot.try_upgrade(convo, task, confidence)
                    if upgraded is not None:
                        return upgraded
                metrics.record("escalation_requested", reason="low_confidence",
                               confidence=confidence, model=config.LOCAL_MODEL)
                return _cloud_or_block(
                    principal,
                    f"Die lokale KI ist sich unsicher (Selbstbewertung "
                    f"{confidence}/10). Soll die Cloud-KI (Claude) zur Hilfe "
                    f"genommen werden?",
                    task,
                    messages,
                )
            metrics.record("local_success", confidence=confidence, model=config.LOCAL_MODEL)
            return _answer(reply, source="local", confidence=confidence)

        # Modell will ein Werkzeug nutzen.
        tool_name = call.get("tool", "")
        tool = TOOLS.get(tool_name)
        if tool is None:
            convo.append({"role": "user", "content": f"Werkzeug '{tool_name}' existiert nicht."})
            continue

        if tool.requires_consent:
            # Werkzeug mit Risiko (Daten nach aussen ODER Code-Ausfuehrung)
            # -> ausdrueckliche Einwilligung noetig.
            if tool.leaves_device:
                reason = (
                    f"Fuer den naechsten Schritt soll das Werkzeug "
                    f"'{tool_name}' genutzt werden, das Daten ins Internet sendet."
                )
            elif tool_name == "run_python":
                reason = (
                    f"Fuer den naechsten Schritt soll das Werkzeug "
                    f"'{tool_name}' lokal Code in einer Sandbox ausfuehren."
                )
            elif tool_name.startswith("mcp__"):
                reason = (
                    f"Fuer den naechsten Schritt soll der externe Skill "
                    f"'{tool_name}' (MCP) ausgefuehrt werden."
                )
            else:
                reason = (
                    f"Fuer den naechsten Schritt soll das Werkzeug "
                    f"'{tool_name}' ausgefuehrt werden."
                )
            metrics.record("tool_consent_requested", tool=tool_name)
            return _consent(
                PendingAction(
                    kind="tool",
                    reason=reason,
                    data_preview=json.dumps(call.get("args", {}), ensure_ascii=False),
                    messages=messages,
                    payload={"call": call, "convo": convo},
                )
            )

        # Lokales Werkzeug -> direkt ausfuehren und weiterdenken.
        result = run_tool(tool_name, **call.get("args", {}))
        convo.append({"role": "assistant", "content": reply})
        convo.append({"role": "user", "content": f"Werkzeug-Ergebnis ({tool_name}):\n{result}"})

    return _answer(
        "Ich konnte die Aufgabe lokal nicht in den erlaubten Schritten abschliessen.",
        source="local",
    )


def resolve_consent(pending_id: str, approved: bool) -> dict:
    """Setzt eine zuvor angeforderte Aktion nach Nutzer-Entscheidung um."""
    action = _PENDING.pop(pending_id, None)
    if action is None:
        return {"type": "error", "text": "Unbekannte oder abgelaufene Anfrage."}

    task = _last_user(action.messages)

    if not approved:
        consent_log.log_event("consent_denied", task=task, data_sent=action.data_preview)
        metrics.record("consent_denied")
        return _answer(
            "Verstanden -- es wurden keine Daten gesendet. "
            "Soll ich es lokal anders versuchen?",
            source="local",
        )

    consent_log.log_event(
        "consent_granted",
        task=task,
        data_sent=action.data_preview,
        model=config.CLOUD_MODEL if action.kind == "cloud" else "",
    )

    if action.kind == "tool":
        return _resume_tool(action)
    if action.kind == "browser":
        return _open_browser(action)
    return _escalate_to_cloud(action)


def _open_browser(action: PendingAction) -> dict:
    """Oeffnet das Abo-Web-Chat im Browser; die Frage geht in die Zwischenablage."""
    prompt = action.payload.get("prompt", "")
    try:
        webbrowser.open(_browser_url(config.BROWSER_PROVIDER, prompt))
    except Exception:  # noqa: BLE001 -- Browser-Oeffnen darf nie crashen
        pass
    metrics.record("browser_handoff", provider=config.BROWSER_PROVIDER)
    label = _provider_label(config.BROWSER_PROVIDER)
    return {
        "type": "manual_cloud",
        "text": (f"Ich habe {label} in deinem Browser geöffnet. Die Frage ist in "
                 "der Zwischenablage – füge sie mit Strg+V ein."),
        "clipboard": prompt,
        "source": "manual",
    }


def _resume_tool(action: PendingAction) -> dict:
    """Fuehrt das genehmigte, Daten-sendende Werkzeug aus und denkt weiter."""
    call = action.payload["call"]
    convo = action.payload["convo"]
    tool_name = call["tool"]
    consent_log.log_event("cloud_call", task=_last_user(action.messages),
                          data_sent=action.data_preview, model=f"tool:{tool_name}")
    result = run_tool(tool_name, **call.get("args", {}))
    convo.append({"role": "assistant", "content": json.dumps(call)})
    convo.append({"role": "user", "content": f"Werkzeug-Ergebnis ({tool_name}):\n{result}"})
    # Verbleibende Verarbeitung wieder lokal.
    return handle_task(convo[1:])  # ohne den System-Prompt am Anfang


def _escalate_to_cloud(action: PendingAction) -> dict:
    """Ruft die Cloud-KI auf (nur nach Einwilligung)."""
    if not cloud_llm.is_configured():
        return {
            "type": "error",
            "text": "Cloud-Notfall nicht moeglich: kein API-Schluessel hinterlegt.",
        }
    consent_log.log_event(
        "cloud_call",
        task=_last_user(action.messages),
        data_sent=action.data_preview,
        model=config.CLOUD_MODEL,
    )
    try:
        text = cloud_llm.chat(action.messages)
    except cloud_llm.CloudLLMError as exc:
        return {"type": "error", "text": str(exc)}
    metrics.record("cloud_answer")
    return _answer(text, source="cloud")
