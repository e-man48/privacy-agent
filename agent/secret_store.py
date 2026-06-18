"""Verschluesselte Ablage von Geheimnissen (API-Schluessel, Passwoerter).

Ziel (DSGVO Art. 32 -- Sicherheit der Verarbeitung): Schluessel liegen NICHT mehr
im Klartext auf der Platte, sondern verschluesselt, gebunden an das Betriebssystem-
Konto des Nutzers -- ohne Master-Passwort, ohne Einrichtungsschritt, ohne fremden
Server (local-first).

Backends (automatisch gewaehlt):
  * Windows: DPAPI (CryptProtectData) -- nur DERSELBE Windows-Nutzer auf DEMSELBEN
    Rechner kann entschluesseln. Keine Zusatz-Abhaengigkeit (ctypes).
  * macOS/Linux: OS-Schluesselbund via 'keyring', falls installiert.
  * Sonst: Klartext-Rueckfall (wie bisher) -- wird als unsicher gemeldet.

In der Einstellungsdatei stehen dann Tokens wie 'enc:dpapi:<base64>' statt der
Schluessel. reveal()/decrypt() machen sie zur Laufzeit wieder lesbar.
"""
from __future__ import annotations

import base64
import os

_PREFIX_DPAPI = "enc:dpapi:"
_PREFIX_KEYRING = "enc:keyring:"
_SERVICE = "PrivacyAgent"


# --- Windows DPAPI (ohne Zusatz-Abhaengigkeit) --------------------------
def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = BLOB()
    func = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    # (pDataIn, szDataDescr, pEntropy, pvReserved, pPromptStruct, dwFlags, pDataOut)
    # dwFlags=0x01 = CRYPTPROTECT_UI_FORBIDDEN (nie einen Dialog zeigen).
    ok = func(ctypes.byref(blob_in), None, None, None, None, 0x01, ctypes.byref(blob_out))
    if not ok:
        raise OSError(("CryptProtectData" if protect else "CryptUnprotectData") + " fehlgeschlagen")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _keyring():
    """Liefert das keyring-Modul mit gesetztem Backend, falls verfuegbar.

    Im gebuendelten Sidecar findet keyrings Entry-Point-Discovery oft kein
    Backend ('fail'-Keyring). Dann setzen wir das passende OS-Backend explizit.
    """
    try:
        import sys
        import keyring  # type: ignore
    except Exception:  # noqa: BLE001  -- nicht installiert
        return None
    try:
        current = type(keyring.get_keyring()).__module__ or ""
        if "fail" in current:
            if sys.platform == "darwin":
                from keyring.backends import macOS  # type: ignore
                keyring.set_keyring(macOS.Keyring())
            elif sys.platform.startswith("linux"):
                from keyring.backends import SecretService  # type: ignore
                keyring.set_keyring(SecretService.Keyring())
    except Exception:  # noqa: BLE001  -- Backend nicht verfuegbar -> Aufrufer faellt zurueck
        pass
    return keyring


def backend() -> str:
    """Welches Verfahren genutzt wird: 'dpapi' | 'keyring' | 'plain'."""
    if os.name == "nt":
        return "dpapi"
    return "keyring" if _keyring() else "plain"


def is_encrypted(value) -> bool:
    return isinstance(value, str) and (
        value.startswith(_PREFIX_DPAPI) or value.startswith(_PREFIX_KEYRING))


def encrypt(name: str, value: str) -> str:
    """Verschluesselt einen Geheimwert in ein speicherbares Token.

    `name` identifiziert das Geheimnis (fuer das keyring-Backend noetig).
    Schlaegt die Verschluesselung fehl, wird der Klartext zurueckgegeben (Rueckfall).
    """
    if not value or is_encrypted(value):
        return value
    if os.name == "nt":
        try:
            blob = _dpapi(value.encode("utf-8"), protect=True)
            return _PREFIX_DPAPI + base64.b64encode(blob).decode("ascii")
        except Exception:  # noqa: BLE001
            pass
    kr = _keyring()
    if kr:
        try:
            kr.set_password(_SERVICE, name, value)
            return _PREFIX_KEYRING + name
        except Exception:  # noqa: BLE001
            pass
    return value  # unverschluesselter Rueckfall


def decrypt(token: str) -> str:
    """Macht ein Token wieder lesbar. Klartext (Legacy) wird unveraendert zurueckgegeben."""
    if not isinstance(token, str):
        return token
    if token.startswith(_PREFIX_DPAPI):
        if os.name != "nt":
            return ""  # auf anderem OS nicht entschluesselbar
        try:
            blob = base64.b64decode(token[len(_PREFIX_DPAPI):])
            return _dpapi(blob, protect=False).decode("utf-8")
        except Exception:  # noqa: BLE001  -- anderer Nutzer/Rechner
            return ""
    if token.startswith(_PREFIX_KEYRING):
        kr = _keyring()
        if not kr:
            return ""
        try:
            return kr.get_password(_SERVICE, token[len(_PREFIX_KEYRING):]) or ""
        except Exception:  # noqa: BLE001
            return ""
    return token  # Legacy-Klartext


def reveal(data: dict) -> dict:
    """Gibt eine Kopie zurueck, in der alle verschluesselten Werte entschluesselt sind."""
    return {k: (decrypt(v) if is_encrypted(v) else v) for k, v in data.items()}
