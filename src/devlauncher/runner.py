"""Service runner: subprocess lifecycle, log streaming, graceful shutdown.

Each service runs as a subprocess with stdout/stderr merged. Two daemon
threads per service consume the output and print it with a colored prefix
([API], [WEB], etc.) so all services are visible in one terminal.

Shutdown is two-phase:
  1. SIGTERM all processes, wait up to 5 seconds each
  2. SIGKILL any that did not exit in time
"""

import os
import queue
import shlex
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import List, Optional

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


@dataclass
class ServiceState:
    """Runtime state for one running service."""
    proc: "subprocess.Popen[str]"
    label: str
    color: str
    port: int
    start_time: float   # time.monotonic() at launch


# ── Log filter (thread-safe) ───────────────────────────────────────────────────

_filter_lock = threading.Lock()
_active_filter: Optional[str] = None


def _get_filter() -> Optional[str]:
    with _filter_lock:
        return _active_filter


def _set_filter(name: Optional[str]) -> None:
    with _filter_lock:
        global _active_filter
        _active_filter = name


def _cycle_log_filter(labels: list) -> None:
    """Advance log filter: None → label[0] → label[1] → ... → None."""
    current = _get_filter()
    if current is None:
        next_filter = labels[0] if labels else None
    else:
        try:
            idx = labels.index(current)
            next_filter = labels[idx + 1] if idx + 1 < len(labels) else None
        except ValueError:
            next_filter = None
    _set_filter(next_filter)
    if next_filter is None:
        print(f"\n{YELLOW}  Showing all services.{RESET}", flush=True)
    else:
        print(f"\n{YELLOW}  Showing only [{next_filter}]. Press l to cycle.{RESET}", flush=True)


# ── Uptime formatting ──────────────────────────────────────────────────────────

def _format_uptime(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    return f"{s // 3600}h {(s % 3600) // 60}m"


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
