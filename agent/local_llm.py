"""Anbindung an die lokale KI ueber Ollama.

Alles hier laeuft ausschliesslich auf dem Geraet des Nutzers -- es verlaesst
keine Information das System. Damit ist dieser Pfad von Natur aus DSGVO-konform.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from typing import Optional

import requests

from . import config
from ._proc import no_window


class LocalLLMError(RuntimeError):
    """Lokale KI nicht erreichbar oder Antwort fehlerhaft."""


def _backend() -> str:
    """Welcher lokale Motor: 'ollama' (Standard) oder 'openai' (kompatibler Server)."""
    return (config.LOCAL_BACKEND or "ollama").strip().lower()


def _openai_base() -> str:
    return config.LOCAL_OPENAI_BASE_URL.rstrip("/")


def _openai_headers() -> dict:
    key = config.LOCAL_OPENAI_API_KEY
    return {"Authorization": f"Bearer {key}"} if key else {}


def supports_native_tools() -> bool:
    """Ollama beherrscht echtes Function-Calling (tools-Parameter)."""
    return _backend() == "ollama"


def chat_tools(messages: list[dict], tools: list[dict],
               model: Optional[str] = None, temperature: float = 0.3) -> dict:
    """Ollama-Chat MIT Werkzeugen (Function-Calling).

    Gibt das Assistenten-Message-Objekt zurueck: {content, tool_calls}. Anders als
    chat() nicht gestreamt (Tool-Aufrufe kommen gebuendelt). `tool_calls` ist eine
    Liste von {function: {name, arguments}} -- leer, wenn das Modell direkt
    antwortet.
    """
    model = model or config.LOCAL_MODEL
    try:
        r = requests.post(
            f"{config.OLLAMA_HOST}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "tools": tools,
                "stream": False,
                "keep_alive": config.OLLAMA_KEEP_ALIVE,
                "options": {"temperature": temperature},
            },
            timeout=(10, config.LOCAL_READ_TIMEOUT),
        )
        r.raise_for_status()
        msg = r.json().get("message", {}) or {}
        return {"content": (msg.get("content") or "").strip(),
                "tool_calls": msg.get("tool_calls") or []}
    except requests.RequestException as exc:
        raise LocalLLMError(f"Lokale KI nicht erreichbar: {exc}") from exc
    except (KeyError, json.JSONDecodeError) as exc:
        raise LocalLLMError(f"Unerwartete Antwort der lokalen KI: {exc}") from exc


def _find_ollama() -> Optional[str]:
    """Findet die ollama-Executable -- auch wenn sie (noch) nicht im PATH steht."""
    found = shutil.which("ollama")
    if found:
        return found
    if os.name == "nt":
        for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", ""),
                     os.environ.get("ProgramW6432", "")):
            if not base:
                continue
            for rel in (("Programs", "Ollama", "ollama.exe"), ("Ollama", "ollama.exe")):
                cand = os.path.join(base, *rel)
                if os.path.isfile(cand):
                    return cand
    return None


_start_lock = threading.Lock()
_last_start = 0.0


def ensure_running(timeout: int = 20) -> bool:
    """Stellt sicher, dass die lokale KI erreichbar ist -- startet Ollama notfalls.

    Verhindert die haeufige 'Lokale KI nicht erreichbar'-Meldung auf Geraeten, wo
    Ollama nicht automatisch (mit-)gestartet ist. Beim OpenAI-Backend gibt es nichts
    zu starten -- dort wird nur geprueft.
    """
    if is_available():
        return True
    if _backend() != "ollama":
        return is_available()

    global _last_start
    with _start_lock:
        if time.time() - _last_start > 15:  # nicht oefter als alle 15s neu versuchen
            exe = _find_ollama()
            if exe:
                try:
                    subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, **no_window())
                    _last_start = time.time()
                except OSError:
                    pass

    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_available():
            return True
        time.sleep(1)
    return False


def is_available() -> bool:
    """Prueft, ob der lokale Motor (Ollama bzw. OpenAI-kompatibler Server) laeuft."""
    if _backend() == "openai":
        try:
            r = requests.get(f"{_openai_base()}/models", timeout=2, headers=_openai_headers())
            return r.status_code < 500
        except requests.RequestException:
            try:  # manche Server haben kein /models -- Basis-URL genuegt
                return requests.get(_openai_base(), timeout=2).status_code < 500
            except requests.RequestException:
                return False
    try:
        r = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=2)
        return r.status_code == 200
    except requests.RequestException:
        return False


def list_models() -> list[str]:
    """Liefert die Namen der verfuegbaren lokalen Modelle."""
    if _backend() == "openai":
        try:
            r = requests.get(f"{_openai_base()}/models", timeout=5, headers=_openai_headers())
            r.raise_for_status()
            return [m.get("id", "") for m in r.json().get("data", []) if m.get("id")]
        except requests.RequestException:
            return []
    try:
        r = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except requests.RequestException:
        return []


def has_model(model: str) -> bool:
    """Prueft, ob das gewuenschte Modell bereit ist."""
    if _backend() == "openai":
        # Ein OpenAI-kompatibler Server liefert, was er geladen hat -- es reicht,
        # dass er erreichbar ist (Modellname ist oft frei waehlbar/egal).
        return is_available()
    try:
        r = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=5)
        r.raise_for_status()
        names = {m["name"] for m in r.json().get("models", [])}
        # Ollama listet z.B. "qwen2.5:7b"; akzeptiere auch ohne :tag.
        return model in names or any(n.split(":")[0] == model.split(":")[0] for n in names)
    except requests.RequestException:
        return False


def chat(messages: list[dict], model: Optional[str] = None, temperature: float = 0.3) -> str:
    """Fuehrt einen Chat-Aufruf gegen die lokale KI aus.

    Waehlt je nach `config.LOCAL_BACKEND` den Motor: Ollama (Standard) oder einen
    beliebigen OpenAI-kompatiblen lokalen Server (llama.cpp, llamafile, LM Studio,
    Jan ...). Beide Pfade nutzen **Streaming**, damit das Lese-Zeitlimit nicht
    waehrend einer langsamen Generierung greift ("Read timed out").
    """
    if _backend() == "openai":
        return _chat_openai(messages, model, temperature)
    return _chat_ollama(messages, model, temperature)


def _chat_ollama(messages: list[dict], model: Optional[str], temperature: float) -> str:
    """Ollama (/api/chat). `keep_alive` haelt das Modell im Speicher (weniger Kaltstarts)."""
    model = model or config.LOCAL_MODEL
    try:
        with requests.post(
            f"{config.OLLAMA_HOST}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": True,
                "keep_alive": config.OLLAMA_KEEP_ALIVE,
                "options": {"temperature": temperature},
            },
            stream=True,
            # (Verbindungs-Timeout, Lese-Timeout je Datenpaket). Das Lese-Timeout
            # wird mit jedem Token zurueckgesetzt -- es greift nur, wenn Ollama
            # gar nichts liefert (z.B. beim erstmaligen Laden eines grossen Modells).
            timeout=(10, config.LOCAL_READ_TIMEOUT),
        ) as r:
            r.raise_for_status()
            parts: list[str] = []
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                obj = json.loads(line)
                if obj.get("error"):
                    raise LocalLLMError(f"Ollama meldet: {obj['error']}")
                chunk = (obj.get("message") or {}).get("content")
                if chunk:
                    parts.append(chunk)
                if obj.get("done"):
                    break
            return "".join(parts).strip()
    except requests.RequestException as exc:
        raise LocalLLMError(f"Lokale KI nicht erreichbar: {exc}") from exc
    except (KeyError, json.JSONDecodeError) as exc:
        raise LocalLLMError(f"Unerwartete Antwort der lokalen KI: {exc}") from exc


def _chat_openai(messages: list[dict], model: Optional[str], temperature: float) -> str:
    """OpenAI-kompatibler lokaler Server (/v1/chat/completions, SSE-Streaming).

    Funktioniert mit llama.cpp `llama-server`, llamafile, LM Studio, Jan u.a.
    """
    model = model or config.LOCAL_OPENAI_MODEL or config.LOCAL_MODEL
    try:
        with requests.post(
            f"{_openai_base()}/chat/completions",
            headers=_openai_headers(),
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "stream": True,
            },
            stream=True,
            timeout=(10, config.LOCAL_READ_TIMEOUT),
        ) as r:
            r.raise_for_status()
            parts: list[str] = []
            for line in r.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                obj = json.loads(data)
                if obj.get("error"):
                    raise LocalLLMError(f"Lokale KI meldet: {obj['error']}")
                delta = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
                if delta:
                    parts.append(delta)
            return "".join(parts).strip()
    except requests.RequestException as exc:
        raise LocalLLMError(
            f"Lokale KI (OpenAI-kompatibel, {_openai_base()}) nicht erreichbar: {exc}"
        ) from exc
    except (KeyError, json.JSONDecodeError) as exc:
        raise LocalLLMError(f"Unerwartete Antwort der lokalen KI: {exc}") from exc


def self_rate(question: str, answer: str) -> int:
    """Laesst das lokale Modell seine eigene Antwort von 0-10 bewerten.

    Liefert eine grobe Konfidenz, die der Router fuer die Eskalations-
    Entscheidung nutzt. Bei Unklarheit wird konservativ 0 zurueckgegeben.
    """
    rating_prompt = [
        {
            "role": "system",
            "content": (
                "Du bewertest, wie sicher und korrekt eine gegebene Antwort die "
                "Frage des Nutzers loest. Antworte mit GENAU einer ganzen Zahl "
                "von 0 (voellig unsicher/falsch) bis 10 (voellig sicher/korrekt). "
                "Keine weiteren Worte."
            ),
        },
        {
            "role": "user",
            "content": f"FRAGE:\n{question}\n\nANTWORT:\n{answer}\n\nBewertung (0-10):",
        },
    ]
    try:
        raw = chat(rating_prompt, temperature=0.0)
    except LocalLLMError:
        return 0
    match = re.search(r"\b(10|\d)\b", raw)
    return int(match.group(1)) if match else 0
