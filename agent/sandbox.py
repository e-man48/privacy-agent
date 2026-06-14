"""Sandbox fuer die lokale Ausfuehrung von (Agenten-generiertem) Python-Code.

Mehrstufige Isolation -- es wird automatisch die staerkste verfuegbare Stufe
gewaehlt:

  1. "docker"      -- starke Isolation: eigener Container OHNE Netzwerk,
                      Speicher-/CPU-/Prozesslimit, read-only Dateisystem,
                      ohne Rechte (cap-drop, no-new-privileges), non-root.
  2. "subprocess"  -- eingeschraenkt: separater Prozess in einem isolierten
                      Temp-Verzeichnis mit bereinigter Umgebung und Zeitlimit.
                      POSIX: zusaetzlich harte Ressourcenlimits (resource).
                      Windows: Job Object mit Speicher-/Prozesslimit und
                      garantiertem Aufraeumen des Prozessbaums.

Hinweis: Stufe 2 ist KEINE vollstaendige Isolation (insbesondere ist der
Netzwerkzugriff nicht zuverlaessig unterbunden). Fuer nicht vertrauenswuerdigen
Code ist Docker dringend zu empfehlen; das Ergebnis nennt die verwendete Stufe.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from typing import Optional

from . import config

_docker_ok: Optional[bool] = None


@dataclass
class SandboxResult:
    output: str
    tier: str          # "docker" | "subprocess"
    timed_out: bool = False


# --- Backend-Auswahl ----------------------------------------------------
def _docker_available() -> bool:
    global _docker_ok
    if _docker_ok is not None:
        return _docker_ok
    if shutil.which("docker") is None:
        _docker_ok = False
        return False
    try:
        r = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=4
        )
        _docker_ok = r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        _docker_ok = False
    return _docker_ok


def run(code: str, timeout: Optional[int] = None) -> SandboxResult:
    """Fuehrt Code in der staerksten verfuegbaren Sandbox-Stufe aus."""
    timeout = timeout or config.SANDBOX_TIMEOUT
    backend = config.SANDBOX_BACKEND
    if backend == "docker" or (backend == "auto" and _docker_available()):
        return _run_docker(code, timeout)
    return _run_subprocess(code, timeout)


# --- Stufe 1: Docker ----------------------------------------------------
def _run_docker(code: str, timeout: int) -> SandboxResult:
    name = "pa-sbx-" + uuid.uuid4().hex[:10]
    mem = f"{config.SANDBOX_MEM_MB}m"
    cmd = [
        "docker", "run", "--rm", "-i", "--name", name,
        "--network", "none",
        "--memory", mem, "--memory-swap", mem,
        "--cpus", "1", "--pids-limit", "64",
        "--read-only", "--tmpfs", "/tmp:rw,size=64m",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "-e", "HOME=/tmp", "-w", "/tmp", "-u", "65534:65534",
        config.SANDBOX_IMAGE, "python", "-I", "-",
    ]
    try:
        p = subprocess.run(
            cmd, input=code, capture_output=True, text=True, timeout=timeout + 8
        )
        out = ((p.stdout or "") + (p.stderr or "")).strip()
        return SandboxResult(out or "(keine Ausgabe)", tier="docker")
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        return SandboxResult(
            f"FEHLER: Zeitlimit ({timeout}s) ueberschritten.", tier="docker", timed_out=True
        )
    except OSError:
        # Docker doch nicht nutzbar -> auf eingeschraenkte Stufe zurueckfallen.
        return _run_subprocess(code, timeout)


# --- Stufe 2: eingeschraenkter Subprozess -------------------------------
def _minimal_env(workdir: str) -> dict:
    """Bereinigte Umgebung -- nur das Noetigste, keine Geheimnisse/Tokens."""
    env = {"TMPDIR": workdir, "TEMP": workdir, "TMP": workdir, "HOME": workdir}
    if os.name == "nt":
        # Windows braucht SystemRoot, sonst startet der Interpreter nicht.
        for key in ("SystemRoot", "SystemDrive", "PATHEXT"):
            if key in os.environ:
                env[key] = os.environ[key]
        env["PATH"] = os.path.dirname(sys.executable)
    else:
        env["PATH"] = "/usr/bin:/bin"
    return env


def _run_subprocess(code: str, timeout: int) -> SandboxResult:
    workdir = tempfile.mkdtemp(prefix="pa-sbx-")
    env = _minimal_env(workdir)
    args = [sys.executable, "-I", "-c", code]
    try:
        if os.name == "nt":
            return _run_windows(args, code, timeout, workdir, env)
        return _run_posix(args, timeout, workdir, env)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _run_posix(args, timeout, workdir, env) -> SandboxResult:
    import resource

    mem_bytes = config.SANDBOX_MEM_MB * 1024 * 1024

    def _limit():  # laeuft im Kindprozess vor exec
        os.setsid()
        resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout + 1))
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))

    try:
        p = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
            cwd=workdir, env=env, preexec_fn=_limit,
        )
        out = ((p.stdout or "") + (p.stderr or "")).strip()
        return SandboxResult(out or "(keine Ausgabe)", tier="subprocess")
    except subprocess.TimeoutExpired:
        return SandboxResult(
            f"FEHLER: Zeitlimit ({timeout}s) ueberschritten.", tier="subprocess", timed_out=True
        )


def _run_windows(args, code, timeout, workdir, env) -> SandboxResult:
    """Windows: Prozess an ein Job Object mit Speicher-/Prozesslimit binden.

    Das Job Object erzwingt ein Speicherlimit pro Prozess, begrenzt die Zahl
    aktiver Prozesse (gegen Fork-Bomben) und raeumt beim Schliessen den
    gesamten Prozessbaum zuverlaessig ab (KILL_ON_JOB_CLOSE).
    """
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
    JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JobObjectExtendedLimitInformation = 9
    CREATE_NO_WINDOW = 0x08000000

    # argtypes/restype explizit setzen, damit 64-Bit-Handles nicht auf int
    # (32 Bit) abgeschnitten werden.
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    job = kernel32.CreateJobObjectW(None, None)
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = (
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        | JOB_OBJECT_LIMIT_PROCESS_MEMORY
    )
    info.BasicLimitInformation.ActiveProcessLimit = 16
    info.ProcessMemoryLimit = config.SANDBOX_MEM_MB * 1024 * 1024
    kernel32.SetInformationJobObject(
        job, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)
    )

    proc = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        cwd=workdir, env=env, creationflags=CREATE_NO_WINDOW,
    )
    # Direkt nach dem Start an das Job Object binden.
    kernel32.AssignProcessToJobObject(job, int(proc._handle))

    timed_out = False
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        kernel32.TerminateJobObject(job, 1)
        proc.kill()
        out, _ = proc.communicate()
    finally:
        kernel32.CloseHandle(job)  # KILL_ON_JOB_CLOSE raeumt Reste ab

    out = (out or "").strip()
    if timed_out:
        return SandboxResult(
            f"FEHLER: Zeitlimit ({timeout}s) ueberschritten.", tier="subprocess", timed_out=True
        )
    return SandboxResult(out or "(keine Ausgabe)", tier="subprocess")
