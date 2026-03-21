# Auto-Discovery in devmux

## What it is

Auto-discovery is devmux's ability to start your services without a `dev.toml`.
It scans the project directory, collects signals, and infers which services exist,
what commands to run, and which ports to use.

It is a **heuristic** — not magic, not a guarantee. Its job is to be right for the
common case and honest when it isn't sure.

---

## Accuracy expectations

| Project type | Expected accuracy |
|---|---|
| Conventional layout (`frontend/`, `api/`, standard tooling) | ~85–90% |
| Slightly unconventional (e.g. `client/` instead of `frontend/`) | ~70–80% |
| Non-standard structure or rare frameworks | ~40–60% |
| Monorepos with 3+ services | Low — use `dev.toml` |

**When accuracy is low, devmux tells you.** It will not silently start the wrong
thing. Low-confidence results surface a warning and a suggestion to run
`devmux init` to generate a `dev.toml` you can review.

---

## How it works: layered signal detection

Auto-discovery does not enumerate every possible stack permutation. Instead, it
assigns a **role** (frontend / backend) to each potential service based on
accumulated evidence. More signals = higher confidence.

### Step 1: Scan candidate directories

devmux looks for directories that could be services. It scans:
- All immediate subdirectories of the project root
- The project root itself

Directories that are clearly not services are skipped:
`.git`, `node_modules`, `__pycache__`, `.venv`, `venv`, `dist`, `build`,
`.next`, `.svelte-kit`, `target`, `coverage`, `docs`, `tests`, `scripts`

### Step 2: Collect signals per directory

For each candidate directory, devmux looks for known files and content:

**Frontend signals**

| Signal | File/condition | Weight |
|---|---|---|
| Has `package.json` with `"dev"` script | `package.json` | HIGH |
| Has `vite.config.*` | `vite.config.ts` / `.js` | HIGH |
| Has `next.config.*` | `next.config.js` / `.ts` | HIGH |
| Has `nuxt.config.*` | `nuxt.config.ts` | HIGH |
| Has `svelte.config.*` | `svelte.config.js` | HIGH |
| Has `package.json` (no `"dev"` script) | `package.json` | MEDIUM |
| Directory named `frontend`, `web`, `client`, `app`, `ui` | dir name | MEDIUM |

**Backend signals**

| Signal | File/condition | Weight |
|---|---|---|
| Has `main.py` + `fastapi` or `uvicorn` in deps | `requirements.txt` / `pyproject.toml` | HIGH |
| Has `manage.py` (Django) | `manage.py` | HIGH |
| Has `app.py` + `flask` in deps | `requirements.txt` | HIGH |
| Has `package.json` with `"start"` or `"dev"` script + no frontend signals | `package.json` | MEDIUM |
| Has `Cargo.toml` + `axum`, `actix-web`, or `rocket` in deps | `Cargo.toml` | HIGH |
| Has `go.mod` | `go.mod` | MEDIUM |
| Has `main.go` | `main.go` | MEDIUM |
| Directory named `api`, `backend`, `server`, `service` | dir name | MEDIUM |

### Step 3: Score and assign roles

Each directory gets a score for each role (frontend / backend). devmux assigns
the **highest scoring directory per role**.

Confidence thresholds:

| Score | Confidence level | Behaviour |
|---|---|---|
| 2+ HIGH signals | CONFIDENT | Start service, no warning |
| 1 HIGH + 1 MEDIUM | LIKELY | Start service, brief note |
| 1 HIGH only | PLAUSIBLE | Start service, suggest verifying |
| MEDIUM signals only | UNCERTAIN | Warn user, still attempt |
| No signals above LOW | SKIP | Do not start, explain why |

### Step 4: Assign default ports

Default ports per framework:

| Framework | Default port |
|---|---|
| Vite (SvelteKit, Vue, React+Vite) | 5173 |
| Next.js | 3000 |
| Nuxt | 3000 |
| Create React App | 3000 |
| FastAPI / uvicorn | 8000 |
| Django | 8000 |
| Flask | 5000 |
| Node.js (Express, Hono, etc.) | 3000 |
| Rust (axum, actix) | 8080 |
| Go | 8080 |

If devmux cannot determine the framework, it defaults to `3000` (backend) or
`5173` (frontend) and tells you.

### Step 5: Infer commands

Commands are inferred from framework detection:

| Detected | Command |
|---|---|
| Vite project | `npm run dev -- --port {self.port}` |
| Next.js | `npm run dev -- -p {self.port}` |
| Nuxt | `npm run dev -- --port {self.port}` |
| FastAPI + uvicorn | `uvicorn main:app --reload --port {self.port}` |
| Django | `python manage.py runserver {self.port}` |
| Flask | `flask run --port {self.port}` |
| Go | `go run . -port {self.port}` |
| Generic `npm run dev` | `npm run dev -- --port {self.port}` |

---

## Failure modes

| Situation | What devmux does |
|---|---|
| Only one service found | Starts it, warns that the other role was not detected |
| Two directories both look like frontends | Picks the one with higher confidence, warns about the other |
| No services detected at all | Exits with a helpful message: "no services detected — run `devmux init`" |
| Framework detected but command uncertain | Uses best-guess command, prints it so the user can verify |
| Monorepo with 3+ services | Detects multiple, warns that `dev.toml` is recommended |

---

## When to use `dev.toml` instead

Auto-discovery is designed for the **common case**. Use a `dev.toml` when:

- Your project has a non-standard directory structure
- You have 3 or more services
- Your start command has custom flags or environment variables
- You use a non-standard port
- You need `{service.port}` cross-references between services
- Auto-discovery picks the wrong thing

Run `devmux init` to generate a `dev.toml` pre-filled with what auto-discovery
found. Edit it from there.

---

## Scope: what devmux will NOT auto-discover

These are out of scope by design:

- **Docker Compose stacks** — use `docker compose up`
- **Kubernetes / Tilt / Skaffold** — wrong abstraction level
- **Services on remote hosts** — devmux is for local dev only
- **Database processes** (Postgres, Redis, etc.) — include in `dev.toml` manually
- **Arbitrary scripts** with no recognised framework signal
- **Monorepos with packages/** structure (pnpm workspaces, turborepo)
  — too many services, too much ambiguity; use `dev.toml`

---

## Summary

Auto-discovery is not a permutation engine. It is a signal collector with a
confidence model. It is most useful for developers who want to run `devmux`
in a new project without writing any config. For anything beyond a
two-service stack with a conventional layout, `dev.toml` is the right tool —
and `devmux init` makes writing it trivial.
