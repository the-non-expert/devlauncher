"""Cross-platform single-keypress reading for interactive terminal commands.

Unix:  Uses termios/tty setcbreak mode + select for non-blocking polling.
       setcbreak (not setraw) preserves output processing so log lines
       don't staircase across the terminal.
Windows: Uses msvcrt.kbhit() + msvcrt.getwch().

Non-TTY stdin (CI, piped): RawTerminal is a no-op; poll_key always returns "".

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
    On non-TTY stdin always returns "".
    """
    if not sys.stdin.isatty():
        return ""
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
