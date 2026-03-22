"""Port detection utilities.

Checks both IPv4 (127.0.0.1) and IPv6 (::1) localhost because Node.js 18+
binds to ::1 by default. Checking only 127.0.0.1 gives false "port free"
results when Vite or other Node-based servers are running.
"""

import socket


def _is_port_free(port: int) -> bool:
    """Return True only if port is free on both IPv4 and IPv6 localhost."""
    for family, addr in [
        (socket.AF_INET,  "127.0.0.1"),
        (socket.AF_INET6, "::1"),
    ]:
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.bind((addr, port))
        except OSError:
            return False
    return True


def find_free_port(start: int) -> int:
    """Return the first free port at or above `start`."""
    port = start
    while not _is_port_free(port):
        port += 1
    return port
