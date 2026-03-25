"""Status file management: write/read/delete .devlauncher.json in project root.

The status file is written on devlauncher start and deleted on graceful exit.
It is a best-effort fallback — the MCP server is the authoritative source.
If devlauncher crashes (SIGKILL, power loss), the file may be left behind.
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .runner import ServiceState

STATUS_FILE = ".devlauncher.json"


def write_status(version: str, pid: int, states: "List[ServiceState]") -> None:
    """Write .devlauncher.json with current service state. Non-fatal on I/O error."""
    services: Dict[str, Any] = {}
    for state in states:
        exit_code = state.proc.poll()
        services[state.label.lower()] = {
            "port": state.port,
            "pid": state.proc.pid,
            "status": "running" if exit_code is None else f"exited({exit_code})",
        }
    data: Dict[str, Any] = {
        "version": version,
        "pid": pid,
        "services": services,
    }
    try:
        Path(STATUS_FILE).write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass  # non-fatal — agent awareness is best-effort


def read_status() -> Optional[Dict[str, Any]]:
    """Read .devlauncher.json. Returns None if not found or invalid."""
    try:
        return json.loads(Path(STATUS_FILE).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def delete_status() -> None:
    """Delete .devlauncher.json if it exists. Non-fatal."""
    try:
        Path(STATUS_FILE).unlink()
    except FileNotFoundError:
        pass
