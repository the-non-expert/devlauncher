"""Service runner: subprocess lifecycle, log streaming, graceful shutdown.

Each service runs as a subprocess with stdout/stderr merged. Two daemon
threads per service consume the output and print it with a colored prefix
([API], [WEB], etc.) so all services are visible in one terminal.

Shutdown is two-phase:
  1. SIGTERM all processes, wait up to 5 seconds each
  2. SIGKILL any that did not exit in time
"""

import os
import shlex
import signal
import subprocess
import sys
import threading
from typing import List

from .config import Service

# ANSI colors — cycling palette for arbitrary number of services
RESET  = "\033[0m"
BOLD   = "\033[1m"
YELLOW = "\033[93m"

_PALETTE = [
    "\033[94m",  # blue
    "\033[92m",  # green
    "\033[95m",  # magenta
    "\033[96m",  # cyan
    "\033[91m",  # red
    "\033[93m",  # yellow
]


def _enable_windows_ansi() -> None:
    """Enable ANSI escape codes in Windows 10+ console."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        ctypes.windll.kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def _stream(proc: subprocess.Popen, label: str, color: str) -> None:
    """Read lines from proc.stdout and print with colored label prefix."""
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            stripped = line.rstrip()
            if stripped:
                print(f"{color}{BOLD}[{label}]{RESET} {stripped}", flush=True)
    except ValueError:
        # Pipe closed (process exited) — normal during shutdown
        pass


def run_services(services: List[Service]) -> None:
    """Start all services, stream their logs, and block until they exit.

    Handles SIGINT (Ctrl+C) and SIGTERM with graceful two-phase shutdown.
    """
    _enable_windows_ansi()

    is_win = sys.platform == "win32"
    procs: list[tuple[subprocess.Popen, str, str]] = []

    for i, svc in enumerate(services):
        color = _PALETTE[i % len(_PALETTE)]
        label = svc.name.upper()

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["FORCE_COLOR"] = "1"
        env.update(svc.env)

        # shlex.split handles quoted args correctly on POSIX; shell=True on Windows
        cmd = svc.cmd if is_win else shlex.split(svc.cmd)

        proc = subprocess.Popen(
            cmd,
            cwd=svc.cwd or None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            shell=is_win,
        )
        procs.append((proc, label, color))
        threading.Thread(
            target=_stream,
            args=(proc, label, color),
            daemon=True,
        ).start()

    def _shutdown(sig=None, frame=None) -> None:
        print(f"\n{YELLOW}⏹  Shutting down...{RESET}", flush=True)
        for proc, _, _ in procs:
            proc.terminate()
        for proc, _, _ in procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Block until all processes exit naturally
    for proc, _, _ in procs:
        proc.wait()
