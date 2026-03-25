# Agent Awareness: MCP Server

devlauncher exposes its state to AI coding agents (Claude Code) so the agent knows services are already running and does not start duplicate processes. Without this, an agent tries to run `uvicorn` or `npm run dev` itself, causing port conflicts and wasted context. The solution: devlauncher writes a status file and runs an MCP server that the agent can query on demand.

---

## How it works: two layers

1. **Status file** (`.devlauncher.json`) — passive, always written, readable by any tool
2. **MCP server** — active, exposes tools to Claude Code for querying status and logs

Zero configuration, zero user action. Works on `pip install`.

---

## Layer 1: Status file (`.devlauncher.json`)

**Location** — project root (same directory as `dev.toml`)

**Lifecycle** — written on `devlauncher` start, deleted on graceful exit

**JSON shape:**

```json
{
  "version": "0.2.0",
  "pid": 12345,
  "services": {
    "api": { "port": 8000, "pid": 38700, "status": "running" },
    "web": { "port": 5173, "pid": 38697, "status": "running" }
  }
}
```

**Fields:**

| Field | Type | Description |
|---|---|---|
| `version` | string | devlauncher version string |
| `pid` | integer | devlauncher's own process ID |
| `services` | object | Map of service name → port/pid/status |

**Stale file handling** — if devlauncher crashes (SIGKILL, power loss), the file may be left behind. The MCP `devlauncher_status()` tool live-checks each service PID via `os.kill(pid, 0)` on every call, so a service that crashed mid-session will show `"crashed"` rather than the stale `"running"` value from the file. The status file itself is not updated on crash.

**`.gitignore` note** — `.devlauncher.json` and `.devlauncher-logs/` are added to `.gitignore` automatically by devlauncher's own `.gitignore`. If you manage your own `.gitignore`, add both entries.

---

## Layer 2: MCP server

Model Context Protocol (MCP) is a standard for tools that AI agents can call. devlauncher registers automatically on `pip install` by writing an entry to `~/.claude/settings.json`. Zero user action required. Transport is stdio — devlauncher runs as an MCP subprocess when Claude Code invokes a tool.

### Tool 1: `devlauncher_status()`

**Parameters** — none

**Returns** — JSON matching the status file shape

**When to call** — at session start, before attempting to start any dev server, or after a restart to verify services came back up

**Example return value:**

```json
{
  "version": "0.2.0",
  "pid": 12345,
  "services": {
    "api": { "port": 8000, "pid": 38700, "status": "running" },
    "web": { "port": 5173, "pid": 38697, "status": "running" }
  }
}
```

### Tool 2: `devlauncher_logs(service, lines)`

**Parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `service` | string | yes | — | Service name (e.g. `"api"`, `"web"`) |
| `lines` | integer | no | 50 | Number of recent log lines to return (max 500) |

**Returns** — JSON with `service`, `lines` (array of strings), `total_available` (lines in buffer)

**When to call** — debugging an error, verifying a server started correctly after code changes, investigating a crash

**ANSI codes** — log lines may contain ANSI escape codes (color sequences) because devlauncher sets `FORCE_COLOR=1` for subprocesses. Strip them if you need plain text.

**Example return value:**

```json
{
  "service": "api",
  "lines": [
    "INFO:     Application startup complete.",
    "INFO:     Uvicorn running on http://0.0.0.0:8000",
    "INFO:     127.0.0.1:54312 - \"GET /health HTTP/1.1\" 200 OK"
  ],
  "total_available": 147
}
```

---

## Agent usage contract

1. **Check before starting** — call `devlauncher_status()` before running `uvicorn`, `npm run dev`, or similar. If services are already running, do not start them again.

2. **Logs are on-demand** — call `devlauncher_logs()` when needed (debugging, verification). Not streamed, not auto-injected.

3. **No remote control** — the agent cannot restart, stop, or modify services. The developer controls lifecycle via interactive keys (r/R/q).

4. **Port awareness** — use ports from the status response when constructing URLs (e.g., `http://localhost:8000`), not hardcoded guesses.

---

## What the MCP server will NOT do

- **Restart or stop services** — the agent is read-only. Restarts go through the developer.
- **Stream logs in real-time** — logs are pulled on demand, not pushed. No WebSocket, no tailing.
- **Inject logs into agent context automatically** — the agent decides when to look at logs, keeping context usage intentional.
- **Work with non-MCP agents out of the box** — Cursor, raw API calls, etc. read the status file directly. The MCP server is for Claude Code.
- **Expose environment variables or secrets** — status and log tools return process metadata and stdout only.

---

## Requirements and compatibility

- Python >= 3.10
- Claude Code with MCP tool support (any version that supports MCP)
- The MCP server is registered globally (`~/.claude/settings.json`), so it is available in all projects where devlauncher is installed
- If devlauncher is not running, the MCP tools return an error response — they do not crash Claude Code
- **Windows note:** `devlauncher_status()` does not detect mid-session service crashes on Windows — a crashed service will continue to show `"running"` until devlauncher exits. All other MCP functionality works normally.

---

## Summary

The MCP server makes devlauncher visible to AI agents so they stop fighting over ports. It is read-only, on-demand, and requires zero setup beyond `pip install`. Agents check status before starting services, pull logs on demand, and respect the developer's control over the lifecycle.
