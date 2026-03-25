"""MCP server for devlauncher agent awareness.

Exposes two tools to Claude Code:
  devlauncher_status()             — running services, ports, PIDs
  devlauncher_logs(service, lines) — last N lines from a service log file

The server is registered in ~/.claude/settings.json on first devlauncher run.
Claude Code spawns it as a subprocess (stdio transport) when a tool is called.
"""

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP

from .runner import RESET, YELLOW
from .status_file import STATUS_FILE

_LOG_DIR = ".devlauncher-logs"
_CLAUDE_SETTINGS = Path.home() / ".claude.json"
_MCP_SERVER_KEY = "devlauncher"
_MCP_SCRIPT = "devlauncher-mcp"


def _mcp_command() -> str:
    """Return the absolute path to devlauncher-mcp, falling back to the bare name."""
    full = shutil.which(_MCP_SCRIPT)
    if full:
        return full
    # Fall back to sibling script next to the current interpreter
    candidate = Path(sys.executable).parent / _MCP_SCRIPT
    if candidate.exists():
        return str(candidate)
    return _MCP_SCRIPT  # last resort — bare name

mcp = FastMCP("devlauncher")


@mcp.tool()
def devlauncher_status() -> Dict[str, Any]:
    """Return the current devlauncher status: running services, ports, and PIDs.

    Call this at the start of a session, before running any dev server command.
    If the response contains {"running": false}, devlauncher is not active and
    you may start services normally.
    """
    try:
        data = json.loads(Path(STATUS_FILE).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"running": False}

    # Live-check each service PID — status file is written at startup only,
    # so a crashed service would still show "running" without this check.
    for svc in data.get("services", {}).values():
        pid = svc.get("pid")
        if pid and svc.get("status") == "running":
            try:
                os.kill(pid, 0)  # signal 0: check liveness without signalling
            except ProcessLookupError:
                svc["status"] = "crashed"
            except PermissionError:
                pass  # process exists, owned by another user — keep "running"

    return data


@mcp.tool()
def devlauncher_logs(service: str, lines: int = 50) -> Dict[str, Any]:
    """Return the last N lines from a service log buffer (max 500).

    Call this when debugging, verifying startup, or investigating a crash.
    Logs are pulled on demand — not streamed.

    Args:
        service: Service name as shown in status (e.g. "api", "web")
        lines: Number of recent log lines to return (default 50, max 500)
    """
    lines = min(max(1, lines), 500)
    log_path = Path(_LOG_DIR) / f"{service.lower()}.log"
    all_lines = _tail(log_path, 500)
    return {
        "service": service,
        "lines": all_lines[-lines:],
        "total_available": len(all_lines),
    }


def _tail(path: Path, n: int) -> List[str]:
    """Read the last n non-empty lines from path. Returns [] if file not found."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        return [line for line in content.splitlines() if line][-n:]
    except FileNotFoundError:
        return []


def ensure_registered() -> None:
    """Register devlauncher MCP server in ~/.claude/settings.json if not already present.

    Idempotent — safe to call on every devlauncher start.
    Non-fatal: prints a warning if registration fails.
    """
    settings_path = _CLAUDE_SETTINGS

    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            settings = {}
    else:
        settings = {}

    mcp_servers = settings.get("mcpServers", {})
    if _MCP_SERVER_KEY in mcp_servers:
        return  # already registered

    mcp_servers[_MCP_SERVER_KEY] = {"command": _mcp_command()}
    settings["mcpServers"] = mcp_servers

    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        print(f"  {YELLOW}✓  Registered devlauncher MCP server with Claude Code.{RESET}", flush=True)
    except OSError as e:
        print(f"  {YELLOW}⚠  Could not register MCP server: {e}{RESET}", flush=True)


def run() -> None:
    """Entry point for the devlauncher-mcp subprocess (stdio transport)."""
    mcp.run()
