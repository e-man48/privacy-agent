"""Kuratierter Katalog empfohlener lokaler Open-Source-Modelle (Ollama).

Wird in der Oberflaeche als Liste mit Haekchen angezeigt -- der Nutzer waehlt
aus und laedt herunter. Die Groessen sind Naeherungswerte der Standard-Variante.
"""
from __future__ import annotations

# name = exakter Ollama-Modellname; tier dient nur der Anzeige/Sortierung.
MODELS: list[dict] = [
    {"name": "qwen2.5:1.5b", "label": "Qwen 2.5 (1.5B)", "size": "~1 GB",
     "tier": "klein", "description": "Sehr klein & schnell – für schwache PCs ohne GPU."},
    {"name": "qwen2.5:3b", "label": "Qwen 2.5 (3B)", "size": "~2 GB",
     "tier": "klein", "description": "Klein, gut auf der CPU nutzbar (Standard für schwache Hardware)."},
    {"name": "llama3.2:3b", "label": "Llama 3.2 (3B)", "size": "~2 GB",
     "tier": "klein", "description": "Metas kleines Modell, flott auf der CPU."},
    {"name": "qwen2.5:7b", "label": "Qwen 2.5 (7B)", "size": "~4.7 GB",
     "tier": "mittel", "description": "Ausgewogen – guter Allrounder, braucht etwas RAM/GPU."},
    {"name": "llama3.1:8b", "label": "Llama 3.1 (8B)", "size": "~4.9 GB",
     "tier": "mittel", "description": "Metas ausgewogenes Modell."},
    {"name": "mistral:7b", "label": "Mistral (7B)", "size": "~4.1 GB",
     "tier": "mittel", "description": "Schnelles, solides Modell von Mistral."},
    {"name": "gemma2:9b", "label": "Gemma 2 (9B)", "size": "~5.4 GB",
     "tier": "mittel", "description": "Googles Modell, stark im Verständnis."},
    {"name": "qwen2.5:14b", "label": "Qwen 2.5 (14B)", "size": "~9 GB",
     "tier": "groß", "description": "Stark – braucht viel RAM oder eine GPU."},
    {"name": "qwen2.5-coder:7b", "label": "Qwen 2.5 Coder (7B)", "size": "~4.7 GB",
     "tier": "spezial", "description": "Auf Programmieren spezialisiert."},
    {"name": "deepseek-r1:7b", "label": "DeepSeek-R1 (7B)", "size": "~4.7 GB",
     "tier": "spezial", "description": "Stark im logischen Schlussfolgern (Reasoning)."},
]


def catalog() -> list[dict]:
    return MODELS
