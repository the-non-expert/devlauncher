# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`devlauncher init` subcommand** — runs auto-discovery and writes `dev.toml` without
  starting services. Useful for reviewing or editing the generated config before the first
  run. Prompts before overwriting an existing `dev.toml`.

## [0.2.0] - 2026-03-25

### Added

- **Interactive keypress commands** — while services are running, press:
  - `r` — soft restart (kill all services, relaunch with current ports and no reinstall)
  - `R` — hard restart (kill all services, re-run install phase, re-resolve ports, relaunch)
  - `s` — print status summary (service name, port, PID, uptime)
  - `l` — cycle log filter (show output for one service at a time, then all)
  - `q` — quit cleanly
- **Cross-platform raw keyboard module** (`keyboard.py`) — uses `tty.setcbreak` on Unix
  (preserves output processing, no staircase artifacts) and `msvcrt` on Windows; degrades
  silently to a no-op on non-TTY stdin (CI, piped input).
- **MCP server for agent awareness** (`mcp_server.py`) — exposes two tools to Claude Code
  via stdio transport:
  - `devlauncher_status()` — running services, ports, PIDs; stale PIDs are live-checked
    with `os.kill(pid, 0)` so a crashed service shows `"crashed"` rather than `"running"`.
  - `devlauncher_logs(service, lines)` — last N lines from a service log file (max 500).
  - The server registers itself in `~/.claude/settings.json` on first run (idempotent).
- **Status file** (`.devlauncher.json`) — written on startup, deleted on graceful exit;
  records version, launcher PID, and per-service port/PID/status. Best-effort: non-fatal
  on I/O error.
- **Log file writing** — each service's stdout/stderr is mirrored to
  `.devlauncher-logs/<service>.log` for on-demand retrieval by the MCP server.
- **`ServiceState` dataclass** in `runner.py` — encapsulates runtime state (process handle,
  label, color, port, start time) for a running service.
- **Log filter helpers** (`_get_filter`, `_set_filter`, `_cycle_log_filter`) — thread-safe
  filter state for the `l` keypress command.
- **Uptime formatter** (`_format_uptime`) — formats elapsed seconds as `Xs`, `Xm Ys`, or
  `Xh Ym`.
- **`devlauncher-mcp` script entry point** in `pyproject.toml` — installed alongside
  `devlauncher` so Claude Code can spawn the MCP server as a subprocess.
- **`mcp` dependency** added to `pyproject.toml`.
- **`.gitignore` entries** for `.devlauncher.json` and `.devlauncher-logs/` so runtime
  artifacts are never accidentally committed.

### Changed

- `run_services()` now returns an action string (`"quit"`, `"soft_restart"`,
  `"hard_restart"`) instead of exiting directly; the new `_restart_loop()` in `cli.py`
  drives the loop.
- Version bumped from `0.1.0` to `0.2.0` in both `pyproject.toml` and
  `src/devlauncher/__init__.py`.

---

## [0.1.0] - 2026-03-24

### Added

- **Initial release** — renamed from `devmux` to `devlauncher`.
- `devlauncher` CLI entry point: reads `dev.toml` or runs auto-discovery when no config
  is present; confirms discovered services with the user and saves a `dev.toml`.
- **Service auto-discovery** — scans the project tree for known frameworks (FastAPI/uvicorn,
  Django, Flask, Rust/Cargo, Go, Node/Vite/npm/bun/pnpm) and infers service definitions.
- **`install_cmd` field** on `Service` — optional command run before a service starts
  (e.g. `npm install`, `pip install -r requirements.txt`).
- **Installer module** (`installer.py`) — `needs_install()` detects whether a lockfile or
  requirements file is present but the corresponding package directory is absent;
  `run_install()` streams the install command output with color-coded prefix.
- **Dependency install phase** in `cli.py` — runs all pending installs sequentially before
  resolving ports or starting services; a non-zero exit code warns but does not abort.
- **Port conflict resolution** — detects in-use ports and finds the next free one;
  `{self.port}` and `{name.port}` references in `cmd` strings are expanded after all ports
  are finalised.
- **Two-phase shutdown** — `SIGINT`/`SIGTERM` sends `SIGTERM` to all child processes, waits
  up to 5 seconds, then sends `SIGKILL` to any survivors.
- **Color-coded multiplexed output** — each service gets a distinct ANSI color; output lines
  are prefixed with `[SERVICE_NAME]`.
- MIT License.
- `pyproject.toml` configured for PyPI packaging.
- `.gitignore` for `__pycache__/`, `*.egg-info/`, `dist/`, `build/`.

[Unreleased]: https://github.com/the-non-expert/devlauncher/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/the-non-expert/devlauncher/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/the-non-expert/devlauncher/releases/tag/v0.1.0
