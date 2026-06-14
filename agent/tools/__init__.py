"""Werkzeuge, die der Agent lokal ausfuehren kann.

Jedes Werkzeug ist bewusst eng gefasst und meldet, ob es das Geraet verlaesst
(`leaves_device`). So kann der Router den Nutzer warnen, bevor z.B. eine
Web-Suche Daten nach aussen gibt.
"""
from .registry import TOOLS, run_tool, tool_descriptions

__all__ = ["TOOLS", "run_tool", "tool_descriptions"]
