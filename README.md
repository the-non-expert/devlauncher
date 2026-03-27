# devlauncher

Start all your dev services with one command.

## The Problem

Every multi-service project means opening multiple terminals, remembering startup commands, and
dealing with silent port conflicts. devlauncher runs everything in one place.

## Install

```
pip install devlauncher
```

Requires Python 3.10+.

## Quickstart

**Zero-config** — run in any project root:

```
cd my-project
devlauncher
```

devlauncher scans your project, detects services (Vite, FastAPI, Django, etc.), shows you what it found,
and asks once to confirm. On confirmation it writes a `dev.toml` and starts everything. It never
asks again.

**Init only** — generate a `dev.toml` to review before running:

```
devlauncher init
```

Runs the same auto-discovery, writes `dev.toml`, and exits without starting any services.
Useful when you want to edit the config first (custom flags, extra services, port overrides).

**Manual** — create a `dev.toml`:

```toml
[services.api]
cmd = "uvicorn main:app --reload --port {self.port}"
port = 8000
cwd = "api"

[services.web]
cmd = "npm run dev -- --port {self.port}"
port = 5173
cwd = "frontend"
env = { VITE_API_URL = "http://localhost:{api.port}" }
```

Then run:

```
devlauncher
```

## How It Works

- Scans subdirectories for framework signals (package.json, requirements.txt, Cargo.toml, etc.)
- Infers services by role (frontend/backend), shows a discovery report
- Prompts once to confirm; writes `dev.toml` so it never asks again
- Runs dependency install phase (`npm install`, `pip install`, etc.) if needed
- Checks ports on both IPv4 and IPv6 — finds a free port if your preferred one is taken
- Starts all services with color-coded, prefixed log output
- Shuts down cleanly on Ctrl+C (SIGTERM → 5s timeout → SIGKILL)

## Interactive Commands

Once services are running, press a key:

| Key | Action |
|-----|--------|
| `r` | Soft restart — kill & restart services (no reinstall) |
| `R` | Hard restart — reinstall deps, re-resolve ports, restart |
| `s` | Status — show PIDs, ports, uptime, running/crashed |
| `l` | Filter logs — cycle: all → [SERVICE] → all |
| `q` / Ctrl+C | Quit — graceful shutdown |

Frontend servers (Vite, Next.js, etc.) handle hot-reload automatically — `r` is mainly useful for backend services.

## Agent Awareness (Claude Code)

devlauncher registers an MCP server with Claude Code on first run. When you open a Claude Code session in a project where devlauncher is running, the agent can:

- Call `devlauncher_status()` to see which services are running, on which ports — so it doesn't start duplicates
- Call `devlauncher_logs(service, lines)` to read recent log output for debugging

Zero configuration required. Works automatically after `pip install devlauncher`.

See [`docs/mcp-server.md`](docs/mcp-server.md) for full details.

## Configuration (dev.toml)

All fields:

```toml
[services.<name>]
cmd         = "command to start this service"          # required
port        = 8000                                     # required; preferred port
cwd         = "subdirectory"                           # optional; default is project root
install_cmd = "pip install -r requirements.txt"        # optional; runs when deps are missing
env         = { KEY = "value" }                        # optional; supports port refs
```

**Port references** — resolved after conflict detection, so they always reflect the actual port in use:

- `{self.port}` — this service's resolved port
- `{api.port}` — another service's resolved port (use the service name as the key)

## Features

- Zero-config auto-discovery (Vite, Next.js, Nuxt, FastAPI, Django, Flask, Go, Rust)
- Dual IPv4 + IPv6 port conflict detection (handles Node.js 18+ IPv6-default binding)
- Dependency install phase with per-service `install_cmd`
- Port reference interpolation (`{self.port}`, `{api.port}`)
- Color-coded, prefixed log output per service
- Graceful shutdown (SIGTERM → 5s timeout → SIGKILL)
- Cross-platform: macOS, Linux, Windows
- `--version` / `-V` flag
- `devlauncher init` — generate `dev.toml` from auto-discovery without starting services
- MCP server for Claude Code agent awareness (zero config)
- Dependencies: `mcp` (all versions), `tomli` (Python 3.9–3.10 only)

## Supported Frameworks (auto-discovery)

| Role | Detected |
|------|----------|
| Frontend | Vite, Next.js, Nuxt, Angular, SvelteKit |
| Backend | FastAPI, Django, Flask, Go, Rust (Cargo) |
| Package managers | npm, yarn, pnpm, bun, pip, go mod |

## License

MIT
