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
from pathlib import Path
from typing import List, Optional

from . import __version__
from .config import Service
from .status_file import delete_status, write_status

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

_LOG_DIR = ".devlauncher-logs"
_log_files: dict = {}


def _open_log_files(states: list) -> None:
    """Open per-service log files for writing. Creates log dir if needed."""
    Path(_LOG_DIR).mkdir(exist_ok=True)
    for state in states:
        _log_files[state.label] = open(
            Path(_LOG_DIR) / f"{state.label.lower()}.log",
            "w",
            encoding="utf-8",
            buffering=1,  # line-buffered
        )


def _close_log_files() -> None:
    """Close all open log file handles."""
    for f in list(_log_files.values()):
        try:
            f.close()
        except Exception:
            pass
    _log_files.clear()


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


# ── Process lifecycle ──────────────────────────────────────────────────────

def _launch_all(services: "List[Service]") -> "list[ServiceState]":
    """Start all service subprocesses and begin log-streaming threads."""
    is_win = sys.platform == "win32"
    states: list = []

    for i, svc in enumerate(services):
        color = _PALETTE[i % len(_PALETTE)]
        label = svc.name.upper()

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["FORCE_COLOR"] = "1"
        env.update(svc.env)

        cmd = svc.cmd if is_win else shlex.split(svc.cmd)

        proc = subprocess.Popen(
            cmd,
            cwd=svc.cwd or None,
            stdin=subprocess.DEVNULL,  # prevents child from stealing keypresses
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            shell=is_win,
            start_new_session=not is_win,  # new process group so SIGTERM reaches all children
        )
        state = ServiceState(
            proc=proc,
            label=label,
            color=color,
            port=svc.port,
            start_time=time.monotonic(),
        )
        states.append(state)
        threading.Thread(
            target=_stream,
            args=(proc, label, color),
            daemon=True,
        ).start()

    return states


def _kill_all(states: list) -> None:
    """Terminate all service process groups. SIGKILL any that don't exit in 5s.

    Uses os.killpg to send SIGTERM to the entire process group, ensuring
    child processes (e.g. vite spawned by npm) are also terminated and
    release their ports before we try to restart.
    """
    for state in states:
        try:
            if sys.platform != "win32":
                os.killpg(os.getpgid(state.proc.pid), signal.SIGTERM)
            else:
                state.proc.terminate()
        except ProcessLookupError:
            pass  # already dead
    for state in states:
        try:
            state.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                if sys.platform != "win32":
                    os.killpg(os.getpgid(state.proc.pid), signal.SIGKILL)
                else:
                    state.proc.kill()
            except ProcessLookupError:
                pass


# ── Display helpers ────────────────────────────────────────────────────────────

def _print_hint_bar() -> None:
    """Print Flutter-style key command hints after services start."""
    print(f"\n{BOLD}  Interactive commands:{RESET}")
    print(f"    r  Soft restart    — kill & restart services (no reinstall)")
    print(f"    R  Hard restart    — reinstall deps, then restart")
    print(f"    s  Status          — show PIDs, ports, uptime")
    print(f"    l  Filter logs     — cycle: all → [SERVICE] → all")
    print(f"    q  Quit            — graceful shutdown (Ctrl+C also works)")
    print(
        f"\n  {YELLOW}Note: frontend servers (Vite, Next.js, etc.) auto-reload on"
        f" file changes.{RESET}"
    )
    print(f"  {'─' * 54}\n", flush=True)


def _print_status(states: list) -> None:
    """Print a status table: service name, PID, port, uptime, alive/crashed."""
    now = time.monotonic()
    print(f"\n{BOLD}  {'SERVICE':<10} {'PID':>7}  {'PORT':>5}  {'UPTIME':>8}  STATUS{RESET}")
    print(f"  {'─'*10}  {'─'*7}  {'─'*5}  {'─'*8}  {'─'*10}")
    for s in states:
        uptime = _format_uptime(now - s.start_time)
        exit_code = s.proc.poll()
        if exit_code is None:
            status = f"\033[92m✓ running\033[0m"
        else:
            status = f"\033[91m✗ exited({exit_code})\033[0m"
        print(
            f"  {s.color}{BOLD}[{s.label}]{RESET}"
            f"  {s.proc.pid:>7}  {s.port:>5}  {uptime:>8}  {status}"
        )
    print(flush=True)


# ── Keyboard listener ──────────────────────────────────────────────────────────

def _keyboard_loop(
    states: list,
    action_queue: "queue.Queue[str]",
    stop_event: threading.Event,
) -> None:
    """Daemon thread: read keypresses and dispatch actions.

    r / R / q  → put action into action_queue (causes run_services to return)
    s          → print status inline (does NOT stop services)
    l          → cycle log filter inline (does NOT stop services)
    Ctrl+C     → treated as quit

    Exits silently if stdin is not a TTY (CI/piped).
    """
    if not sys.stdin.isatty():
        return

    from .keyboard import RawTerminal, poll_key

    labels = [s.label for s in states]

    with RawTerminal():
        while not stop_event.is_set():
            key = poll_key(stop_event)
            if not key:
                continue
            if key == "r":
                print(f"\n{YELLOW}  ↻  Soft restarting...{RESET}\n", flush=True)
                action_queue.put("soft_restart")
                return
            elif key == "R":
                print(f"\n{YELLOW}  ↻  Hard restarting (reinstalling deps)...{RESET}\n", flush=True)
                action_queue.put("hard_restart")
                return
            elif key in ("q", "\x03"):
                action_queue.put("quit")
                return
            elif key == "s":
                _print_status(states)
            elif key == "l":
                _cycle_log_filter(labels)


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
    """Read lines from proc.stdout and print with colored label prefix.

    Respects the active log filter — if a filter is set, only lines from
    the matching service are printed. All lines are written to the log file
    regardless of the active filter.
    """
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            stripped = line.rstrip()
            if stripped:
                active = _get_filter()
                if active is None or active == label:
                    print(f"{color}{BOLD}[{label}]{RESET} {stripped}", flush=True)
                f = _log_files.get(label)
                if f and not f.closed:
                    f.write(stripped + "\n")
                    f.flush()
    except ValueError:
        pass


def run_services(services: List[Service]) -> str:
    """Start all services, stream their logs, listen for keypresses.

    Returns one of:
        "soft_restart"  — caller should restart services without reinstall
        "hard_restart"  — caller should reinstall deps then restart
        "quit"          — caller should exit

    Handles SIGINT/SIGTERM by pushing "quit" into the action queue.
    """
    _enable_windows_ansi()
    _set_filter(None)

    states = _launch_all(services)
    _open_log_files(states)
    write_status(__version__, os.getpid(), states)
    _print_hint_bar()

    action_q: queue.Queue = queue.Queue()
    stop_event = threading.Event()

    def _on_signal(sig=None, frame=None) -> None:
        action_q.put("quit")

    signal.signal(signal.SIGINT,  _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    kb_thread = threading.Thread(
        target=_keyboard_loop,
        args=(states, action_q, stop_event),
        daemon=True,
    )
    kb_thread.start()

    while True:
        try:
            action = action_q.get(timeout=0.5)
            break
        except queue.Empty:
            if all(s.proc.poll() is not None for s in states):
                action = "quit"
                break

    stop_event.set()
    _kill_all(states)
    _close_log_files()
    delete_status()

    if action == "quit":
        print(f"\n{YELLOW}⏹  Shutting down...{RESET}", flush=True)

    return action
