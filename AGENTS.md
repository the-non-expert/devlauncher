# devlauncher — Agent Reference

Structured reference for AI agents and coding assistants. No prose.

---

## What it is

- **Package**: devlauncher
- **Type**: Python CLI tool
- **Install**: `pip install devlauncher`
- **Version**: 0.1.0
- **Python**: 3.9+
- **Purpose**: Starts multiple local dev services (e.g. API + frontend) from one terminal
- **Entry point**: `devlauncher.cli:main`
- **Config file**: `dev.toml` (TOML format, auto-written on first run if absent)
- **External deps**: none on Python 3.11+; `tomli` required on 3.9–3.10

---

## CLI Usage

```
devlauncher                    # reads ./dev.toml, or runs auto-discovery if not present
devlauncher path/to/dev.toml   # explicit config path
python -m devlauncher          # equivalent to devlauncher
```

No flags or subcommands. Single optional positional argument: path to a TOML config file.

---

## dev.toml Schema

Each service is defined under `[services.<name>]`.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `cmd` | string | yes | — | Shell command to start the service. Supports port refs. |
| `port` | int | yes | — | Preferred port. Reassigned automatically if taken. |
| `cwd` | string | no | `"."` | Working directory relative to project root. |
| `install_cmd` | string | no | `null` | Command to install dependencies. Run before startup if deps are missing. |
| `env` | table | no | `{}` | Environment variables injected into the process. Values support port refs. |

Example:

```toml
[services.api]
cmd = "uvicorn main:app --reload --port {self.port}"
port = 8000
cwd = "api"
install_cmd = "pip install -r requirements.txt"

[services.web]
cmd = "npm run dev -- --port {self.port}"
port = 5173
cwd = "frontend"
install_cmd = "npm install"
env = { VITE_API_URL = "http://localhost:{api.port}" }
```

---

## Auto-Discovery Behavior

Triggered when no `dev.toml` exists and no explicit config path is given.

1. Scans immediate subdirectories for framework signals (weighted scoring)
2. Scores each dir for frontend/backend role: HIGH=3, MEDIUM=2, LOW=1
3. Picks highest-scoring dir per role; computes confidence:
   - CONFIDENT (≥6), LIKELY (4–5), PLAUSIBLE (3), UNCERTAIN (1–2), SKIP (0)
4. Displays discovery report table to user
5. Prompts: `Start these services? [Y/n]`
6. On Y: writes `dev.toml` to project root → starts services (never prompts again)
7. On N: exits; user must create `dev.toml` manually

Detected signals by framework:

| Framework | Role | Key signals |
|-----------|------|-------------|
| Vite / SvelteKit | frontend | `vite.config.*`, `package.json` with vite dep |
| Next.js | frontend | `next.config.*`, `package.json` with next dep |
| Nuxt | frontend | `nuxt.config.*`, `package.json` with nuxt dep |
| Angular | frontend | `angular.json` |
| FastAPI | backend | `requirements.txt` with fastapi, uvicorn |
| Django | backend | `manage.py` |
| Flask | backend | `requirements.txt` with flask |
| Go | backend | `go.mod` |
| Rust | backend | `Cargo.toml` |

---

## Port Reference Syntax

Placeholders in `cmd` and `env` values. Resolved after port conflict detection — always reflect the actual port in use.

| Syntax | Resolves to |
|--------|-------------|
| `{self.port}` | This service's actual resolved port |
| `{<name>.port}` | Another service's resolved port (use the service name) |

Example: if `api` lands on 8001 due to a conflict, `{api.port}` in the web service's env resolves to 8001 automatically.

---

## Install Phase

Runs sequentially before services start.

- Triggered per service when `install_cmd` is set AND `needs_install()` returns true
- `needs_install()` logic:
  - Node: `node_modules/` is absent OR lock file is newer than `node_modules/`
  - Python: no `.venv`, `venv`, or `env` directory present
  - Go: always runs (idempotent)
- Non-zero exit from `install_cmd` prints a warning but does not abort startup

---

## Exit Behavior

- Ctrl+C sends SIGTERM to all service subprocesses
- If a process does not exit within 5 seconds, SIGKILL is sent
- All processes are waited on before devlauncher exits
- Windows: uses `process.terminate()` (no SIGTERM/SIGKILL distinction)
- Exit codes: 0 on clean shutdown, 1 on config error

---

## Known Limitations

- Auto-discovery detects at most one frontend and one backend service per project
- Monorepo layouts (`packages/`, `apps/` with 2+ subdirs) produce a warning; manual `dev.toml` recommended
- UNCERTAIN confidence services (score 1–2) are skipped automatically
- `devlauncher init` is **not implemented** — do not suggest it or reference it
- `tomli` must be installed manually on Python 3.9–3.10 if not declared in the consuming project's own dependencies
