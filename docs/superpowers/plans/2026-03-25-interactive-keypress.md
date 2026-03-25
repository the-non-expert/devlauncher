# Interactive Keypress Commands Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Flutter-style interactive keypress commands (`r`, `R`, `s`, `l`, `q`) to devlauncher so developers can soft-restart, hard-restart, check status, filter logs, and quit — all from the running terminal.

**Architecture:** A new `keyboard.py` module handles cross-platform raw terminal I/O. `runner.py` is refactored to extract process lifecycle helpers and returns an action string instead of calling `sys.exit()`. `cli.py` wraps the runner in a restart loop that handles reinstall + re-resolve on hard restart.

**Tech Stack:** Python stdlib only — `termios`/`tty`/`select` (Unix), `msvcrt` (Windows), `threading`, `queue`, `dataclasses`, `time`.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/devlauncher/keyboard.py` | **Create** | Raw terminal mode, cross-platform single-key reads |
| `src/devlauncher/runner.py` | **Modify** | ServiceState dataclass, process lifecycle helpers, log filter, hint bar, status display, keyboard loop, refactored `run_services()` |
| `src/devlauncher/cli.py` | **Modify** | Restart loop wrapping `run_services()` |
| `tests/test_runner_interactive.py` | **Create** | Unit tests for pure runner helpers |
| `tests/test_cli_restart_loop.py` | **Create** | Unit tests for restart loop logic |

---

## Task 1: `keyboard.py` — cross-platform raw key reads

**Files:**
- Create: `src/devlauncher/keyboard.py`

The keyboard module provides one thing: a way to read single keypresses without waiting for Enter, cross-platform.

- [ ] **Step 1: Create `src/devlauncher/keyboard.py`**

```python
"""Cross-platform single-keypress reading for interactive terminal commands.

Unix:  Uses termios/tty to set raw mode + select for non-blocking polling.
Windows: Uses msvcrt.kbhit() + msvcrt.getwch().

Usage (from a daemon thread):
    with RawTerminal():
        while not stop_event.is_set():
            key = poll_key(stop_event)
            if key:
                handle(key)
"""

import sys
import threading


class RawTerminal:
    """Context manager: put the terminal into cbreak (single-char, no echo) mode.

    Uses tty.setcbreak (not setraw) so that output processing is preserved —
    printed lines still emit carriage returns, preventing staircase artifacts
    when log output mixes with interactive input.

    On Windows this is a no-op — msvcrt already works character-by-character.
    On non-TTY stdin (CI, piped input) this is also a no-op so the tool
    degrades gracefully without crashing.
    """

    def __enter__(self) -> "RawTerminal":
        self._active = False
        if sys.platform == "win32" or not sys.stdin.isatty():
            return self
        import termios
        import tty
        self._fd = sys.stdin.fileno()
        self._old_settings = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)   # preserves output processing; DO NOT use setraw
        self._active = True
        return self

    def __exit__(self, *_) -> None:
        if not getattr(self, "_active", False):
            return
        import termios
        termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_settings)


def poll_key(stop_event: threading.Event, timeout: float = 0.2) -> str:
    """Return the next keypress, or empty string if none within timeout.

    Designed to be called in a loop so stop_event can be checked between polls.
    Never blocks longer than `timeout` seconds.
    """
    if sys.platform == "win32":
        import msvcrt
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if stop_event.is_set():
                return ""
            if msvcrt.kbhit():
                return msvcrt.getwch()
            time.sleep(0.02)
        return ""
    else:
        import select
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if ready and not stop_event.is_set():
            return sys.stdin.read(1)
        return ""
```

- [ ] **Step 2: Commit**

```bash
git add src/devlauncher/keyboard.py
git commit -m "feat: add cross-platform raw keyboard module"
```

---

## Task 2: Pure helpers in `runner.py` — ServiceState, uptime, log filter

**Files:**
- Modify: `src/devlauncher/runner.py`
- Create: `tests/test_runner_interactive.py`

These are all pure/mockable units that can be TDD'd cleanly.

- [ ] **Step 1: Write failing tests for `_format_uptime` and `_cycle_log_filter`**

Create `tests/test_runner_interactive.py`:

```python
"""Tests for pure runner helpers added for interactive keypress feature."""
import time
import pytest


def test_format_uptime_under_a_minute():
    from devlauncher.runner import _format_uptime
    assert _format_uptime(0) == "0s"
    assert _format_uptime(1) == "1s"
    assert _format_uptime(59) == "59s"


def test_format_uptime_minutes():
    from devlauncher.runner import _format_uptime
    assert _format_uptime(60) == "1m 0s"
    assert _format_uptime(90) == "1m 30s"
    assert _format_uptime(3599) == "59m 59s"


def test_format_uptime_hours():
    from devlauncher.runner import _format_uptime
    assert _format_uptime(3600) == "1h 0m"
    assert _format_uptime(7384) == "2h 3m"


def test_cycle_log_filter_none_to_first():
    from devlauncher.runner import _cycle_log_filter, _get_filter, _set_filter
    _set_filter(None)
    _cycle_log_filter(["API", "WEB"])
    assert _get_filter() == "API"


def test_cycle_log_filter_wraps_to_next():
    from devlauncher.runner import _cycle_log_filter, _get_filter, _set_filter
    _set_filter("API")
    _cycle_log_filter(["API", "WEB"])
    assert _get_filter() == "WEB"


def test_cycle_log_filter_wraps_to_none():
    from devlauncher.runner import _cycle_log_filter, _get_filter, _set_filter
    _set_filter("WEB")
    _cycle_log_filter(["API", "WEB"])
    assert _get_filter() is None


def test_cycle_log_filter_single_service_wraps():
    from devlauncher.runner import _cycle_log_filter, _get_filter, _set_filter
    _set_filter(None)
    _cycle_log_filter(["API"])
    assert _get_filter() == "API"
    _cycle_log_filter(["API"])
    assert _get_filter() is None
```

- [ ] **Step 2: Run tests — expect ImportError / AttributeError (they must fail)**

```bash
cd /Users/ayushj/My-Github/devmux && python -m pytest tests/test_runner_interactive.py -v 2>&1 | head -40
```

Expected: `ImportError: cannot import name '_format_uptime'`

- [ ] **Step 3: Add helpers to `runner.py`**

At the top of `runner.py`, after the imports, add:

```python
import queue
import time
from dataclasses import dataclass
from typing import Optional
```

Add these definitions after the `_PALETTE` block:

```python
@dataclass
class ServiceState:
    """Runtime state for one running service."""
    proc: "subprocess.Popen[str]"
    label: str      # uppercase service name e.g. "API"
    color: str      # ANSI color code
    port: int
    start_time: float   # time.monotonic() at launch


# ── Log filter (thread-safe) ───────────────────────────────────────────────────

_filter_lock = threading.Lock()
_active_filter: Optional[str] = None   # None = show all services


def _get_filter() -> Optional[str]:
    with _filter_lock:
        return _active_filter


def _set_filter(name: Optional[str]) -> None:
    with _filter_lock:
        global _active_filter
        _active_filter = name


def _cycle_log_filter(labels: list[str]) -> None:
    """Advance the log filter: None → label[0] → label[1] → ... → None."""
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
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
cd /Users/ayushj/My-Github/devmux && python -m pytest tests/test_runner_interactive.py -v
```

Expected: 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/devlauncher/runner.py tests/test_runner_interactive.py
git commit -m "feat: add ServiceState, log filter, and uptime helpers to runner"
```

---

## Task 3: Process lifecycle helpers — `_launch_all`, `_kill_all`

**Files:**
- Modify: `src/devlauncher/runner.py`
- Modify: `tests/test_runner_interactive.py`

Extract process start/stop from the monolithic `run_services()` so they can be tested and reused in the restart loop.

- [ ] **Step 1: Write failing tests for `_kill_all`**

Append to `tests/test_runner_interactive.py`:

```python
# ── _kill_all ──────────────────────────────────────────────────────────────────

def _make_state(terminated_quickly: bool) -> "ServiceState":
    """Build a ServiceState with a mocked proc."""
    from unittest.mock import MagicMock
    from devlauncher.runner import ServiceState
    proc = MagicMock()
    proc.poll.return_value = None
    if terminated_quickly:
        proc.wait.return_value = 0
    else:
        import subprocess
        proc.wait.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=5)
    return ServiceState(proc=proc, label="API", color="", port=8000, start_time=0.0)


def test_kill_all_terminates_running_procs():
    from devlauncher.runner import _kill_all
    state = _make_state(terminated_quickly=True)
    _kill_all([state])
    state.proc.terminate.assert_called_once()


def test_kill_all_force_kills_on_timeout():
    from devlauncher.runner import _kill_all
    state = _make_state(terminated_quickly=False)
    _kill_all([state])
    state.proc.terminate.assert_called_once()
    state.proc.kill.assert_called_once()


def test_kill_all_empty_list_is_noop():
    from devlauncher.runner import _kill_all
    _kill_all([])  # must not raise
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd /Users/ayushj/My-Github/devmux && python -m pytest tests/test_runner_interactive.py::test_kill_all_terminates_running_procs -v
```

- [ ] **Step 3: Add `_launch_all` and `_kill_all` to `runner.py`**

Add after the uptime helper:

```python
# ── Process lifecycle ──────────────────────────────────────────────────────────

def _launch_all(services: List[Service]) -> list[ServiceState]:
    """Start all service subprocesses and begin log-streaming threads.

    Returns a ServiceState for each running service.
    """
    is_win = sys.platform == "win32"
    states: list[ServiceState] = []

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
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            shell=is_win,
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


def _kill_all(states: list[ServiceState]) -> None:
    """Terminate all service processes. SIGKILL any that don't exit in 5s."""
    for state in states:
        state.proc.terminate()
    for state in states:
        try:
            state.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            state.proc.kill()
```

- [ ] **Step 4: Update `_stream` to respect log filter**

Replace the existing `_stream` function:

```python
def _stream(proc: subprocess.Popen, label: str, color: str) -> None:
    """Read lines from proc.stdout and print with colored label prefix.

    Respects the active log filter — if a filter is set, only lines from
    the matching service are printed.
    """
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            stripped = line.rstrip()
            if stripped:
                active = _get_filter()
                if active is None or active == label:
                    print(f"{color}{BOLD}[{label}]{RESET} {stripped}", flush=True)
    except ValueError:
        pass
```

- [ ] **Step 5: Run all tests — expect pass**

```bash
cd /Users/ayushj/My-Github/devmux && python -m pytest tests/test_runner_interactive.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/devlauncher/runner.py tests/test_runner_interactive.py
git commit -m "feat: extract _launch_all and _kill_all process lifecycle helpers"
```

---

## Task 4: Hint bar and status display

**Files:**
- Modify: `src/devlauncher/runner.py`
- Modify: `tests/test_runner_interactive.py`

The Flutter-style hint bar is shown once after service URLs. Status is printed on demand when `s` is pressed.

- [ ] **Step 1: Write failing test for `_print_status`**

Append to `tests/test_runner_interactive.py`:

```python
# ── _print_status ──────────────────────────────────────────────────────────────

def test_print_status_shows_all_services(capsys):
    from unittest.mock import MagicMock
    from devlauncher.runner import ServiceState, _print_status
    proc = MagicMock()
    proc.pid = 42
    proc.poll.return_value = None   # still running
    state = ServiceState(proc=proc, label="API", color="", port=8000, start_time=0.0)
    _print_status([state])
    out = capsys.readouterr().out
    assert "API" in out
    assert "8000" in out
    assert "42" in out


def test_print_status_shows_crashed_service(capsys):
    from unittest.mock import MagicMock
    from devlauncher.runner import ServiceState, _print_status
    proc = MagicMock()
    proc.pid = 99
    proc.poll.return_value = 1   # exited with error
    state = ServiceState(proc=proc, label="WEB", color="", port=5173, start_time=0.0)
    _print_status([state])
    out = capsys.readouterr().out
    assert "crashed" in out.lower() or "exited" in out.lower()
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd /Users/ayushj/My-Github/devmux && python -m pytest tests/test_runner_interactive.py::test_print_status_shows_all_services -v
```

- [ ] **Step 3: Add `_print_hint_bar` and `_print_status` to `runner.py`**

```python
# ── Display helpers ────────────────────────────────────────────────────────────

def _print_hint_bar() -> None:
    """Print Flutter-style key command hints after services start.

    Note: frontend dev servers (Vite, Next.js, Nuxt) handle their own
    hot-reloading via HMR. r/R are mainly useful for backend services.
    """
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


def _print_status(states: list[ServiceState]) -> None:
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
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd /Users/ayushj/My-Github/devmux && python -m pytest tests/test_runner_interactive.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/devlauncher/runner.py tests/test_runner_interactive.py
git commit -m "feat: add hint bar and status display to runner"
```

---

## Task 5: Keyboard loop + refactor `run_services()` to return action

**Files:**
- Modify: `src/devlauncher/runner.py`

This is the core change. `run_services()` goes from "blocks forever, calls sys.exit" to "blocks until a key action, returns action string". The keyboard loop runs as a daemon thread.

- [ ] **Step 1: Add keyboard loop to `runner.py`**

Add after `_print_status`:

```python
# ── Keyboard listener ──────────────────────────────────────────────────────────

def _keyboard_loop(
    states: list[ServiceState],
    action_queue: "queue.Queue[str]",
    stop_event: threading.Event,
) -> None:
    """Daemon thread: read keypresses and dispatch actions.

    r / R / q  → put action into action_queue (causes run_services to return)
    s          → print status inline (does NOT stop services)
    l          → cycle log filter inline (does NOT stop services)
    Ctrl+C     → treated as quit
    """
    from .keyboard import RawTerminal, poll_key

    # Non-TTY environments (CI, piped stdin): disable interactive keys silently
    if not sys.stdin.isatty():
        return

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
            elif key in ("q", "\x03"):   # q or Ctrl+C
                action_queue.put("quit")
                return
            elif key == "s":
                _print_status(states)
            elif key == "l":
                _cycle_log_filter(labels)
```

- [ ] **Step 2: Replace `run_services()` with the new refactored version**

Remove the existing `run_services` function (lines 63-117) and replace with:

```python
def run_services(services: List[Service]) -> str:
    """Start all services, stream their logs, listen for keypresses.

    Returns one of:
        "soft_restart"  — caller should restart services without reinstall
        "hard_restart"  — caller should reinstall deps then restart
        "quit"          — caller should exit

    Handles SIGINT/SIGTERM by pushing "quit" into the action queue.
    """
    _enable_windows_ansi()
    _set_filter(None)   # reset any previous log filter on each (re)start

    states = _launch_all(services)
    _print_hint_bar()

    action_q: queue.Queue[str] = queue.Queue()
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

    # Wait: either a key action arrives, or all processes die naturally
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

    if action == "quit":
        print(f"\n{YELLOW}⏹  Shutting down...{RESET}", flush=True)

    return action
```

- [ ] **Step 3: Verify the module imports cleanly**

```bash
cd /Users/ayushj/My-Github/devmux && python -c "from devlauncher.runner import run_services; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Run existing + new tests**

```bash
cd /Users/ayushj/My-Github/devmux && python -m pytest tests/ -v
```

Expected: all pass (the old `run_services` is replaced but we haven't broken imports yet — the next task updates cli.py).

- [ ] **Step 5: Commit**

```bash
git add src/devlauncher/runner.py src/devlauncher/keyboard.py
git commit -m "feat: add keyboard loop and refactor run_services to return action string"
```

---

## Task 6: Restart loop in `cli.py`

**Files:**
- Modify: `src/devlauncher/cli.py`
- Create: `tests/test_cli_restart_loop.py`

`cli.py` now wraps `run_services()` in a loop, handling soft/hard restart and quit.

- [ ] **Step 1: Write failing tests**

Create `tests/test_cli_restart_loop.py`:

```python
"""Tests for the restart loop in cli.py."""
from unittest.mock import MagicMock, call, patch
import pytest


def _make_services():
    from devlauncher.config import Service
    return [Service(name="api", cmd="uvicorn main:app", port=8000)]


def test_quit_action_exits_immediately():
    """run_services returning 'quit' should stop the loop."""
    services = _make_services()
    with patch("devlauncher.cli.run_services", return_value="quit") as mock_run, \
         patch("devlauncher.cli._run_install_phase"), \
         patch("devlauncher.cli._resolve_services", return_value=services):
        from devlauncher.cli import _restart_loop
        _restart_loop(services, services)
    mock_run.assert_called_once()


def test_soft_restart_does_not_reinstall():
    """Soft restart should call run_services twice but _run_install_phase once."""
    services = _make_services()
    run_calls = iter(["soft_restart", "quit"])
    with patch("devlauncher.cli.run_services", side_effect=run_calls) as mock_run, \
         patch("devlauncher.cli._run_install_phase") as mock_install, \
         patch("devlauncher.cli._resolve_services", return_value=services):
        from devlauncher.cli import _restart_loop
        _restart_loop(services, services)
    assert mock_run.call_count == 2
    mock_install.assert_not_called()


def test_hard_restart_reinstalls_and_reruns():
    """Hard restart should call _run_install_phase and run_services again."""
    services = _make_services()
    run_calls = iter(["hard_restart", "quit"])
    with patch("devlauncher.cli.run_services", side_effect=run_calls) as mock_run, \
         patch("devlauncher.cli._run_install_phase") as mock_install, \
         patch("devlauncher.cli._resolve_services", return_value=services):
        from devlauncher.cli import _restart_loop
        _restart_loop(services, services)
    assert mock_run.call_count == 2
    mock_install.assert_called_once()


def test_hard_restart_re_resolves_ports():
    """Hard restart must re-resolve ports in case something grabbed one."""
    services = _make_services()
    run_calls = iter(["hard_restart", "quit"])
    with patch("devlauncher.cli.run_services", side_effect=run_calls), \
         patch("devlauncher.cli._run_install_phase"), \
         patch("devlauncher.cli._resolve_services", return_value=services) as mock_resolve:
        from devlauncher.cli import _restart_loop
        _restart_loop(services, services)
    # Called once inside _restart_loop during the hard restart branch.
    # The initial port resolution happens in main() before _restart_loop is called.
    assert mock_resolve.call_count == 1
```

- [ ] **Step 2: Run — expect ImportError for `_restart_loop`**

```bash
cd /Users/ayushj/My-Github/devmux && python -m pytest tests/test_cli_restart_loop.py -v 2>&1 | head -20
```

- [ ] **Step 3: Add `_restart_loop` to `cli.py` and update `main()`**

In `cli.py`, add this function just before `main()`:

```python
def _restart_loop(services: List[Service], original_services: List[Service]) -> None:
    """Run services in a loop, handling soft/hard restart and quit actions.

    Args:
        services:          Already-resolved services (correct ports, refs expanded).
        original_services: Pre-resolution services from config — used to re-resolve
                           ports on hard restart in case ports have changed.
    """
    while True:
        action = run_services(services)

        if action == "quit":
            sys.exit(0)

        elif action == "soft_restart":
            # Re-use same services (same ports, same commands — no reinstall)
            print(f"\n{BOLD}Restarting...{RESET}\n", flush=True)
            # services unchanged — loop restarts them as-is

        elif action == "hard_restart":
            # Reinstall deps, then re-resolve ports (a port may have been grabbed)
            print(f"\n{BOLD}Hard restarting...{RESET}\n", flush=True)
            _run_install_phase(original_services)
            services = _resolve_services(original_services)
```

Then replace the last two lines of `main()`:

```python
    # Before (old):
    run_services(services)

    # After (new):
    _restart_loop(services, services)
```

The full bottom of `main()` after the startup header block becomes:

```python
    # Print startup header
    print(f"\n{BOLD}devlauncher{RESET}")
    for i, svc in enumerate(services):
        color = _PALETTE[i % len(_PALETTE)]
        print(f"  {color}{BOLD}[{svc.name.upper()}]{RESET} http://localhost:{svc.port}")
    print()

    _restart_loop(services, services)
```

- [ ] **Step 4: Run all tests**

```bash
cd /Users/ayushj/My-Github/devmux && python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Smoke test (manual)**

```bash
cd /Users/ayushj/My-Github/devmux && python -m devlauncher --help 2>&1 || true
python -c "from devlauncher.cli import main; print('imports OK')"
```

- [ ] **Step 6: Commit**

```bash
git add src/devlauncher/cli.py tests/test_cli_restart_loop.py
git commit -m "feat: add restart loop to cli — soft restart, hard restart, quit"
```

---

## Task 7: Version bump + pyproject.toml update

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/devlauncher/__init__.py`

- [ ] **Step 1: Check current version**

```bash
grep version /Users/ayushj/My-Github/devmux/pyproject.toml
grep version /Users/ayushj/My-Github/devmux/src/devlauncher/__init__.py 2>/dev/null || echo "no __init__ version"
```

- [ ] **Step 2: Bump to 0.2.0**

In `pyproject.toml`, change:
```toml
version = "0.1.0"
```
to:
```toml
version = "0.2.0"
```

If `__init__.py` has a `__version__` string, update it too.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml src/devlauncher/__init__.py
git commit -m "chore: bump version to 0.2.0"
```

---

## Task 8: Full test run + final validation

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/ayushj/My-Github/devmux && python -m pytest tests/ -v --tb=short
```

Expected: all tests pass, no warnings about imports.

- [ ] **Step 2: Verify clean import**

```bash
python -c "
from devlauncher.keyboard import RawTerminal, poll_key
from devlauncher.runner import run_services, _format_uptime, _cycle_log_filter, _kill_all, _print_status
from devlauncher.cli import main, _restart_loop
print('All imports OK')
"
```

- [ ] **Step 3: Final commit if anything was missed**

```bash
git status
# If clean: nothing to do
# If dirty: add + commit
```

---

## Summary of changes

```
src/devlauncher/
  keyboard.py          ← NEW: RawTerminal, poll_key
  runner.py            ← MODIFIED: ServiceState, filter, uptime, hint bar,
                                   status, _launch_all, _kill_all,
                                   _keyboard_loop, refactored run_services()
  cli.py               ← MODIFIED: _restart_loop, main() updated

tests/
  test_runner_interactive.py  ← NEW: 14 unit tests
  test_cli_restart_loop.py    ← NEW: 4 unit tests
```

### What each key does

| Key | Action | Notes |
|-----|--------|-------|
| `r` | Soft restart | Kills & relaunches services — no reinstall. Fast. |
| `R` | Hard restart | Reinstall deps → re-resolve ports → relaunch. Full reset. |
| `s` | Status | Inline table: PID, port, uptime, running/crashed. Services keep running. |
| `l` | Filter logs | Cycles: all → [API] → [WEB] → all. Services keep running. |
| `q` / Ctrl+C | Quit | Graceful SIGTERM → 5s → SIGKILL. |

### Flutter-style hint bar (shown once at startup)

```
  Interactive commands:
    r  Soft restart    — kill & restart services (no reinstall)
    R  Hard restart    — reinstall deps, then restart
    s  Status          — show PIDs, ports, uptime
    l  Filter logs     — cycle: all → [SERVICE] → all
    q  Quit            — graceful shutdown (Ctrl+C also works)

  Note: frontend servers (Vite, Next.js, etc.) auto-reload on file changes.
  ──────────────────────────────────────────────────────
```
