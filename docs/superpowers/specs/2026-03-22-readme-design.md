---
title: README + AGENTS.md Design
date: 2026-03-22
status: approved
---

# README + AGENTS.md Design for devmux

## Context

devmux is a pip-installable Python CLI (v0.1.0) that starts multiple dev services in one terminal
with zero-config auto-discovery and port conflict detection. Being prepared for PyPI launch.

## Goals

- README: human-facing, terse, direct. Audience = general full-stack devs running multi-service projects.
- AGENTS.md: agent-facing fact-file, structured for LLM parsing. No prose.
- Both files serve as the PyPI landing page (README) and AI assistant reference (AGENTS.md).

## Tone

Minimal prose. Developer-to-developer. No storytelling, no marketing fluff.

## README.md Structure

### 1. Title + tagline
`# devmux` — one-line description of what it does.

### 2. The Problem (2-3 sentences max)
Terse. Every multi-service project requires opening and managing multiple terminals.
Ports conflict silently. Services start in the wrong order. devmux fixes this.

### 3. Install
```
pip install devmux
```
Single command. No prerequisites section needed.

### 4. Quickstart
Two paths shown side-by-side or sequentially:
- **Zero-config**: run `devmux` in a project root — auto-detects services, prompts once, writes dev.toml, never asks again.
- **Manual**: create a minimal `dev.toml` with two services, run `devmux`.
Total: ~10 lines of commands/config.

### 5. How It Works
Bullet list only. No paragraphs.
- Scans project directory for framework signals
- Infers services (frontend/backend), shows discovery report
- Prompts user once to confirm
- Writes dev.toml (never auto-discovers again)
- Runs dependency install phase (npm install, pip install, etc.)
- Detects port conflicts on both IPv4 and IPv6
- Starts all services with color-coded, prefixed logs
- Graceful shutdown on Ctrl+C (SIGTERM → SIGKILL fallback)

### 6. Configuration (dev.toml)
Annotated minimal example showing all fields:
```toml
[services.api]
cmd = "uvicorn main:app --port {self.port}"
port = 8000
install_cmd = "pip install -r requirements.txt"

[services.web]
cmd = "npm run dev -- --port {self.port}"
port = 5173
install_cmd = "npm install"
env = { VITE_API_URL = "http://localhost:{api.port}" }
```
Explain `{self.port}` and `{service.port}` inline as code comments or a single note.

### 7. Features
Tight bullet list:
- Zero-config auto-discovery (Vite, Next.js, Nuxt, FastAPI, Django, Flask, Go, Rust)
- Dual IPv4 + IPv6 port conflict detection (handles Node.js 18+ IPv6-default binding)
- Dependency install phase with per-service install_cmd
- Port reference interpolation (`{self.port}`, `{api.port}`)
- Color-coded, prefixed log output per service
- Graceful shutdown (SIGTERM → 5s timeout → SIGKILL)
- Cross-platform: macOS, Linux, Windows
- Zero external dependencies on Python 3.11+ (tomli required on 3.9–3.10)

### 8. Supported Frameworks (auto-discovery)
Small two-column table: Role | Frameworks

| Role | Detected |
|------|----------|
| Frontend | Vite, Next.js, Nuxt, Angular, SvelteKit |
| Backend | FastAPI, Django, Flask, Go, Rust (Cargo) |
| Package managers | npm, yarn, pnpm, bun, pip, go mod |

### 9. License
MIT — one line.

---

## AGENTS.md Structure

Flat, structured, no prose. Designed for LLM ingestion.

### Sections

1. **What it is** — one paragraph, machine-readable facts: name, purpose, language, install method, entry point
2. **CLI usage** — all commands and flags with types and defaults
3. **dev.toml schema** — every field, type, default, and description in a table
4. **Auto-discovery behavior** — how it works, what signals it detects, confidence levels, what gets written
5. **Port reference syntax** — `{self.port}` and `{name.port}` with examples
6. **Install phase** — when it runs, what install_cmd does, how needs_install is determined
7. **Exit behavior** — shutdown sequence, signal handling, exit codes
8. **Known limitations** — monorepo caveats, uncertain confidence, manual override via dev.toml

---

## Files to Create

| File | Location | Purpose |
|------|----------|---------|
| README.md | `/` (repo root) | Human-facing, PyPI landing page |
| AGENTS.md | `/` (repo root) | AI agent reference |

## Out of Scope

- Comparison table vs. Honcho/Overmind/Foreman (skip — defensive, goes stale)
- Changelog section (too early, v0.1.0)
- Contributing guide (can be added post-launch)
- Badges/shields (optional, can add after PyPI publish with real URLs)
- `devmux init` subcommand — referenced in source code warning messages but NOT implemented. Do NOT mention it in README or AGENTS.md.
