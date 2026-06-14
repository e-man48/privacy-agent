"""Principal -- wer mit dem Agenten spricht, mit welchen Rechten.

Ermoeglicht Pro-Person-Trennung:
  * jeder Principal hat einen eigenen Gedaechtnis-Bereich (`scope`);
  * Rechte pro Person, z.B. ob er die (bezahlte) Cloud freigeben darf.

Der lokale GUI-Nutzer ist ein vollberechtigter Principal; Matrix-Nutzer werden
anhand der Konfiguration eingestuft.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import config


@dataclass
class Principal:
    id: str                 # eindeutige Kennung (z.B. Matrix-ID oder "local")
    name: str               # Anzeigename
    can_use_cloud: bool = True
    scope: str = "shared"   # Gedaechtnis-Bereich dieser Person


def gui() -> Principal:
    """Der lokale Nutzer der Desktop-GUI -- volle Rechte, eigener Bereich."""
    return Principal(id="local", name="GUI", can_use_cloud=True, scope="local")


def for_matrix(user_id: str) -> Principal:
    """Stuft einen Matrix-Nutzer anhand der Admin-Liste ein.

    Ist keine Admin-Liste gesetzt, duerfen alle erlaubten Nutzer die Cloud
    freigeben (abwaertskompatibel). Sonst nur die gelisteten Admins.
    """
    admins = config.matrix_admin_users()
    can_cloud = (user_id in admins) if admins else True
    return Principal(id=user_id, name=user_id, can_use_cloud=can_cloud, scope=user_id)
