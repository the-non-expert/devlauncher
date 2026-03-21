# Auto-Install Dependency Bootstrapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Before starting services, devmux detects missing dependencies and runs the appropriate install command automatically — so a fresh clone or worktree just works.

**Architecture:** Add an optional `install_cmd` field to `Service` (inferred by discovery, overridable in dev.toml). A new `installer.py` module checks whether deps are present (missing `node_modules/`, no `.venv/`, etc.) and runs the install command with colored `[INSTALL:NAME]` output before services start. Install failures warn but do not block startup.

**Tech Stack:** Python 3.9+, stdlib only (`subprocess`, `pathlib`, `shlex`, `threading`) — no new dependencies.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/devmux/config.py` | Add `install_cmd: Optional[str]` to `Service`; parse + serialize it |
| Modify | `src/devmux/discovery.py` | Infer `install_cmd` per service; serialize in `services_to_toml()` |
| Create | `src/devmux/installer.py` | `needs_install()` detection + `run_install()` execution |
| Modify | `src/devmux/cli.py` | Call install phase after load, before `_resolve_services()` |
| Create | `tests/test_config.py` | Tests for `install_cmd` parsing and serialization |
| Create | `tests/test_installer.py` | Tests for detection and install execution |
| Create | `tests/test_discovery_install.py` | Tests for `_infer_install_cmd()` |

---

## Task 1: Add `install_cmd` to `Service` and TOML I/O

**Files:**
- Modify: `src/devmux/config.py`
- Modify: `src/devmux/discovery.py` (only `services_to_toml`)
- Create: `tests/test_config.py`

- [ ] **Step 1.1: Write failing tests**

Create `tests/test_config.py`:

```python
"""Tests for Service.install_cmd parsing and serialization."""
import textwrap
import pytest
from devmux.config import Service, load_config, resolve_port_refs
from devmux.discovery import services_to_toml


# ── Service dataclass ──────────────────────────────────────────────────────────

def test_service_install_cmd_defaults_to_none():
    svc = Service(name="api", cmd="uvicorn main:app", port=8000)
    assert svc.install_cmd is None


def test_service_install_cmd_set():
    svc = Service(name="api", cmd="uvicorn main:app", port=8000,
                  install_cmd="pip install -r requirements.txt")
    assert svc.install_cmd == "pip install -r requirements.txt"


# ── load_config ────────────────────────────────────────────────────────────────

def test_load_config_without_install_cmd(tmp_path):
    (tmp_path / "dev.toml").write_text(textwrap.dedent("""
        [services.api]
        cmd = "uvicorn main:app --reload"
        port = 8000
    """))
    services = load_config(str(tmp_path / "dev.toml"))
    assert services[0].install_cmd is None


def test_load_config_with_install_cmd(tmp_path):
    (tmp_path / "dev.toml").write_text(textwrap.dedent("""
        [services.api]
        cmd = "uvicorn main:app --reload"
        port = 8000
        install_cmd = "pip install -r requirements.txt"
    """))
    services = load_config(str(tmp_path / "dev.toml"))
    assert services[0].install_cmd == "pip install -r requirements.txt"


# ── services_to_toml ───────────────────────────────────────────────────────────

def test_services_to_toml_without_install_cmd():
    services = [Service(name="api", cmd="uvicorn main:app", port=8000)]
    toml = services_to_toml(services)
    assert "install_cmd" not in toml


def test_services_to_toml_with_install_cmd():
    services = [Service(name="api", cmd="uvicorn main:app", port=8000,
                        install_cmd="pip install -r requirements.txt")]
    toml = services_to_toml(services)
    assert 'install_cmd = "pip install -r requirements.txt"' in toml


def test_roundtrip_install_cmd(tmp_path):
    """Write dev.toml with install_cmd, read it back, values match."""
    services = [Service(name="web", cmd="npm run dev", port=5173,
                        install_cmd="npm install")]
    toml_content = services_to_toml(services)
    config_file = tmp_path / "dev.toml"
    config_file.write_text(toml_content)
    loaded = load_config(str(config_file))
    assert loaded[0].install_cmd == "npm install"
```

- [ ] **Step 1.2: Run tests to confirm they fail**

```bash
cd /Users/ayushj/My-Github/devmux
python -m pytest tests/test_config.py -v
```

Expected: `TypeError` or `unexpected keyword argument 'install_cmd'`

- [ ] **Step 1.3: Add `install_cmd` to `Service` in `config.py`**

In `src/devmux/config.py`, add `Optional` to the import and update `Service`:

```python
from typing import Dict, List, Optional  # add Optional
```

Update the dataclass (after `env` field):

```python
@dataclass(frozen=True)
class Service:
    name: str
    cmd: str
    port: int
    cwd: str = "."
    env: Dict[str, str] = field(default_factory=dict)
    install_cmd: Optional[str] = None
```

- [ ] **Step 1.4: Parse `install_cmd` in `load_config()`**

In `load_config()`, update the `Service(...)` constructor call:

```python
services.append(Service(
    name=name,
    cmd=cfg["cmd"],
    port=int(cfg["port"]),
    cwd=cfg.get("cwd", "."),
    env={k: str(v) for k, v in cfg.get("env", {}).items()},
    install_cmd=cfg.get("install_cmd") or None,
))
```

- [ ] **Step 1.5: Serialize `install_cmd` in `services_to_toml()` in `discovery.py`**

In `services_to_toml()`, add after the `cwd` line:

```python
if svc.install_cmd:
    lines.append(f'install_cmd = "{svc.install_cmd}"')
```

- [ ] **Step 1.6: Run tests to confirm they pass**

```bash
python -m pytest tests/test_config.py -v
```

Expected: all 7 tests PASS

- [ ] **Step 1.7: Commit**

```bash
git add src/devmux/config.py src/devmux/discovery.py tests/test_config.py
git commit -m "feat: add install_cmd field to Service with TOML parse/serialize support"
```

---

## Task 2: Create `installer.py` with detection and execution

**Files:**
- Create: `src/devmux/installer.py`
- Create: `tests/test_installer.py`

- [ ] **Step 2.1: Write failing tests for `needs_install()`**

Create `tests/test_installer.py`:

```python
"""Tests for dependency detection and install execution."""
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from devmux.config import Service
from devmux.installer import needs_install, run_install


# ── Helpers ────────────────────────────────────────────────────────────────────

def _svc(cwd: str, install_cmd: str) -> Service:
    return Service(name="test", cmd="echo hi", port=3000,
                   cwd=cwd, install_cmd=install_cmd)


# ── needs_install: no install_cmd ─────────────────────────────────────────────

def test_needs_install_returns_false_when_no_install_cmd(tmp_path):
    svc = Service(name="api", cmd="uvicorn main:app", port=8000,
                  cwd=str(tmp_path))
    assert needs_install(svc) is False


# ── needs_install: Node.js ─────────────────────────────────────────────────────

def test_needs_install_node_missing_node_modules(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts":{"dev":"vite"}}')
    svc = _svc(str(tmp_path), "npm install")
    assert needs_install(svc) is True


def test_needs_install_node_present_node_modules(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts":{"dev":"vite"}}')
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    svc = _svc(str(tmp_path), "npm install")
    assert needs_install(svc) is False


def test_needs_install_node_stale_lock_file(tmp_path):
    """node_modules exists but lock file is newer → needs install."""
    import time
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    time.sleep(0.01)  # ensure lock file is strictly newer
    lock = tmp_path / "package-lock.json"
    lock.write_text("{}")
    svc = _svc(str(tmp_path), "npm install")
    assert needs_install(svc) is True


def test_needs_install_node_fresh_lock_file(tmp_path):
    """Lock file older than node_modules → no install needed."""
    import time
    lock = tmp_path / "package-lock.json"
    lock.write_text("{}")
    time.sleep(0.01)
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    svc = _svc(str(tmp_path), "npm install")
    assert needs_install(svc) is False


def test_needs_install_yarn_works_same_as_npm(tmp_path):
    (tmp_path / "yarn.lock").write_text("")
    svc = _svc(str(tmp_path), "yarn install")
    assert needs_install(svc) is True  # no node_modules


def test_needs_install_pnpm_works(tmp_path):
    (tmp_path / "node_modules").mkdir()
    svc = _svc(str(tmp_path), "pnpm install")
    assert needs_install(svc) is False


def test_needs_install_bun_works(tmp_path):
    svc = _svc(str(tmp_path), "bun install")
    assert needs_install(svc) is True  # no node_modules


# ── needs_install: Python ──────────────────────────────────────────────────────

def test_needs_install_python_no_venv(tmp_path):
    (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n")
    svc = _svc(str(tmp_path), "pip install -r requirements.txt")
    assert needs_install(svc) is True


def test_needs_install_python_dotenv_exists(tmp_path):
    (tmp_path / ".venv").mkdir()
    svc = _svc(str(tmp_path), "pip install -r requirements.txt")
    assert needs_install(svc) is False


def test_needs_install_python_venv_exists(tmp_path):
    (tmp_path / "venv").mkdir()
    svc = _svc(str(tmp_path), "pip install -r requirements.txt")
    assert needs_install(svc) is False


def test_needs_install_python_env_exists(tmp_path):
    (tmp_path / "env").mkdir()
    svc = _svc(str(tmp_path), "pip install -e .")
    assert needs_install(svc) is False


# ── needs_install: Go ──────────────────────────────────────────────────────────

def test_needs_install_go_always_true(tmp_path):
    """go mod download is idempotent — always run it."""
    svc = _svc(str(tmp_path), "go mod download")
    assert needs_install(svc) is True


# ── run_install ────────────────────────────────────────────────────────────────

def test_run_install_returns_zero_on_success(tmp_path, capsys):
    svc = Service(name="web", cmd="npm run dev", port=5173,
                  cwd=str(tmp_path), install_cmd="echo installed")
    exit_code = run_install(svc, color="\033[94m")
    assert exit_code == 0


def test_run_install_returns_nonzero_on_failure(tmp_path):
    svc = Service(name="web", cmd="npm run dev", port=5173,
                  cwd=str(tmp_path), install_cmd="false")  # 'false' exits 1
    if sys.platform == "win32":
        pytest.skip("'false' not available on Windows")
    exit_code = run_install(svc, color="\033[94m")
    assert exit_code != 0


def test_run_install_streams_output(tmp_path, capsys):
    svc = Service(name="api", cmd="uvicorn main:app", port=8000,
                  cwd=str(tmp_path), install_cmd="echo hello-from-install")
    run_install(svc, color="\033[92m")
    captured = capsys.readouterr()
    assert "hello-from-install" in captured.out
    assert "INSTALL:API" in captured.out
```

- [ ] **Step 2.2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_installer.py -v
```

Expected: `ModuleNotFoundError: No module named 'devmux.installer'`

- [ ] **Step 2.3: Implement `installer.py`**

Create `src/devmux/installer.py`:

```python
"""Dependency install detection and execution.

Before starting services, devmux checks whether dependencies are present
and runs the appropriate install command if not.

Detection heuristics:
  Node.js  — node_modules/ missing, or lock file newer than node_modules/
  Python   — no .venv/, venv/, or env/ directory present
  Go       — go mod download is idempotent; always run
"""

import shlex
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Service

# Re-export ANSI codes used for [INSTALL:NAME] labels
from .runner import BOLD, RESET

_NODE_INSTALL_PREFIXES = ("npm install", "yarn install", "pnpm install", "bun install")
_NODE_LOCK_FILES = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb")
_PYTHON_VENV_DIRS = (".venv", "venv", "env")


def needs_install(service: "Service") -> bool:
    """Return True if the service's dependencies need to be installed.

    Returns False immediately if service.install_cmd is None or empty.
    """
    if not service.install_cmd:
        return False

    cwd = Path(service.cwd)
    cmd = service.install_cmd

    # ── Node.js ────────────────────────────────────────────────────────────────
    if any(cmd.startswith(prefix) for prefix in _NODE_INSTALL_PREFIXES):
        node_modules = cwd / "node_modules"
        if not node_modules.exists():
            return True
        # Stale check: any lock file newer than node_modules/ → reinstall
        nm_mtime = node_modules.stat().st_mtime
        for lock_name in _NODE_LOCK_FILES:
            lock_path = cwd / lock_name
            if lock_path.exists() and lock_path.stat().st_mtime > nm_mtime:
                return True
        return False

    # ── Python ─────────────────────────────────────────────────────────────────
    if "pip install" in cmd:
        for venv_dir in _PYTHON_VENV_DIRS:
            if (cwd / venv_dir).is_dir():
                return False
        return True

    # ── Go: go mod download is fast and idempotent — always run ───────────────
    if cmd.startswith("go mod download"):
        return True

    return False


def run_install(service: "Service", color: str) -> int:
    """Run service.install_cmd, streaming output with a colored label prefix.

    Returns the process exit code. Callers should warn on non-zero but
    should NOT abort — services can still start even if install partially
    fails (e.g. optional dev deps).
    """
    label = f"INSTALL:{service.name.upper()}"
    is_win = sys.platform == "win32"
    cmd = service.install_cmd  # guaranteed non-None by caller

    print(f"{color}{BOLD}[{label}]{RESET} {cmd}", flush=True)

    proc = subprocess.Popen(
        cmd if is_win else shlex.split(cmd),
        cwd=service.cwd or None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        shell=is_win,
    )

    for line in proc.stdout:  # type: ignore[union-attr]
        stripped = line.rstrip()
        if stripped:
            print(f"{color}{BOLD}[{label}]{RESET} {stripped}", flush=True)

    proc.wait()
    return proc.returncode
```

- [ ] **Step 2.4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_installer.py -v
```

Expected: all tests PASS

- [ ] **Step 2.5: Commit**

```bash
git add src/devmux/installer.py tests/test_installer.py
git commit -m "feat: add installer.py with needs_install detection and run_install execution"
```

---

## Task 3: Infer `install_cmd` in `discovery.py`

**Files:**
- Modify: `src/devmux/discovery.py`
- Create: `tests/test_discovery_install.py`

- [ ] **Step 3.1: Write failing tests**

Create `tests/test_discovery_install.py`:

```python
"""Tests for install_cmd inference in auto-discovery."""
import json
from pathlib import Path

import pytest

from devmux.discovery import discover_services


def _write_pkg_json(directory: Path, scripts=None, deps=None) -> None:
    pkg = {"scripts": scripts or {"dev": "vite"}, "dependencies": deps or {}}
    (directory / "package.json").write_text(json.dumps(pkg))


# ── Node frontend ──────────────────────────────────────────────────────────────

def test_discovers_npm_install_for_vite_frontend(tmp_path):
    fe = tmp_path / "frontend"
    fe.mkdir()
    _write_pkg_json(fe, deps={"vite": "^5.0.0"})
    (fe / "vite.config.ts").write_text("")
    services, _ = discover_services(str(tmp_path))
    web = next((s for s in services if s.name == "web"), None)
    assert web is not None
    assert web.install_cmd == "npm install"


def test_discovers_yarn_install_for_yarn_project(tmp_path):
    fe = tmp_path / "frontend"
    fe.mkdir()
    _write_pkg_json(fe, deps={"vite": "^5.0.0"})
    (fe / "vite.config.ts").write_text("")
    (fe / "yarn.lock").write_text("")
    services, _ = discover_services(str(tmp_path))
    web = next((s for s in services if s.name == "web"), None)
    assert web is not None
    assert web.install_cmd == "yarn install"


def test_discovers_pnpm_install_for_pnpm_project(tmp_path):
    fe = tmp_path / "frontend"
    fe.mkdir()
    _write_pkg_json(fe, deps={"vite": "^5.0.0"})
    (fe / "vite.config.ts").write_text("")
    (fe / "pnpm-lock.yaml").write_text("")
    services, _ = discover_services(str(tmp_path))
    web = next((s for s in services if s.name == "web"), None)
    assert web is not None
    assert web.install_cmd == "pnpm install"


# ── Python backend ─────────────────────────────────────────────────────────────

def test_discovers_pip_install_for_fastapi_with_requirements(tmp_path):
    api = tmp_path / "api"
    api.mkdir()
    (api / "requirements.txt").write_text("fastapi\nuvicorn\n")
    (api / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")
    services, _ = discover_services(str(tmp_path))
    svc = next((s for s in services if s.name == "api"), None)
    assert svc is not None
    assert svc.install_cmd == "pip install -r requirements.txt"


def test_discovers_pip_install_e_for_pyproject_only(tmp_path):
    api = tmp_path / "api"
    api.mkdir()
    (api / "pyproject.toml").write_text(
        '[project]\nname="myapi"\n[project.dependencies]\nfastapi="*"\nuvicorn="*"\n'
    )
    (api / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")
    services, _ = discover_services(str(tmp_path))
    svc = next((s for s in services if s.name == "api"), None)
    assert svc is not None
    assert svc.install_cmd == "pip install -e ."


# ── Go backend ─────────────────────────────────────────────────────────────────

def test_discovers_go_mod_download_for_go_backend(tmp_path):
    api = tmp_path / "api"
    api.mkdir()
    (api / "go.mod").write_text("module example.com/myapp\n\ngo 1.21\n")
    (api / "main.go").write_text('package main\nfunc main() {}\n')
    services, _ = discover_services(str(tmp_path))
    svc = next((s for s in services if s.name == "api"), None)
    assert svc is not None
    assert svc.install_cmd == "go mod download"


# ── Rust backend ───────────────────────────────────────────────────────────────

def test_no_install_cmd_for_rust_backend(tmp_path):
    api = tmp_path / "api"
    api.mkdir()
    (api / "Cargo.toml").write_text('[package]\nname="myapp"\nversion="0.1.0"\n[dependencies]\naxum="*"\n')
    services, _ = discover_services(str(tmp_path))
    svc = next((s for s in services if s.name == "api"), None)
    # Rust: cargo handles deps itself, no install_cmd
    if svc:
        assert svc.install_cmd is None


# ── services_to_toml includes install_cmd ─────────────────────────────────────

def test_services_to_toml_includes_install_cmd(tmp_path):
    fe = tmp_path / "frontend"
    fe.mkdir()
    _write_pkg_json(fe, deps={"vite": "^5.0.0"})
    (fe / "vite.config.ts").write_text("")
    services, _ = discover_services(str(tmp_path))
    from devmux.discovery import services_to_toml
    toml = services_to_toml(services)
    assert "install_cmd" in toml
    assert "npm install" in toml
```

- [ ] **Step 3.2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_discovery_install.py -v
```

Expected: failures because `install_cmd` is None on all discovered services

- [ ] **Step 3.3: Add `_infer_install_cmd()` to `discovery.py`**

Add this function after `_infer_backend()` in `discovery.py`:

```python
def _infer_install_cmd(score: _DirScore) -> Optional[str]:
    """Return the dependency install command for a scored directory, or None.

    Priority:
      - Node.js (package.json present): use detected package manager
      - Python backend (requirements.txt or pyproject.toml): pip install
      - Go backend (go.mod): go mod download
      - Rust: None (cargo handles deps during cargo run)
    """
    directory = score.path

    # Node.js (any package.json — frontend or node backend)
    if (directory / "package.json").exists():
        pm = score.package_manager
        return f"{pm} install"

    # Python backends
    if score.backend_framework in ("fastapi", "flask", "django", "python"):
        if (directory / "requirements.txt").exists():
            return "pip install -r requirements.txt"
        if (directory / "pyproject.toml").exists():
            return "pip install -e ."
        return None

    # Go
    if score.backend_framework == "go":
        return "go mod download"

    return None
```

- [ ] **Step 3.4: Wire `install_cmd` into `discover_services()` for both frontend and backend**

In `discover_services()`, update both `Service(...)` constructor calls:

For the frontend service (around line 396):
```python
services.append(Service(
    name="web",
    cmd=cmd,
    port=port,
    cwd=cwd,
    env={},
    install_cmd=_infer_install_cmd(fs),
))
```

For the backend service (around line 421):
```python
services.append(Service(
    name="api",
    cmd=cmd,
    port=port,
    cwd=cwd,
    env={},
    install_cmd=_infer_install_cmd(bs),
))
```

- [ ] **Step 3.5: Run tests to confirm they pass**

```bash
python -m pytest tests/test_discovery_install.py -v
```

Expected: all tests PASS

- [ ] **Step 3.6: Run all tests to confirm nothing is broken**

```bash
python -m pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 3.7: Commit**

```bash
git add src/devmux/discovery.py tests/test_discovery_install.py
git commit -m "feat: infer install_cmd per service during auto-discovery"
```

---

## Task 4: Wire install phase into `cli.py`

**Files:**
- Modify: `src/devmux/cli.py`

No unit tests for cli.py — the install path is covered by installer.py tests. Manual verification below.

- [ ] **Step 4.1: Add `_run_install_phase()` helper and call it in `main()`**

In `src/devmux/cli.py`, add the import:

```python
from .installer import needs_install, run_install
```

Add this helper function before `main()`:

```python
def _run_install_phase(services: List[Service]) -> None:
    """Run dependency installs for any service that needs them.

    Installs run sequentially (not in parallel) so output stays readable.
    A non-zero exit code from an install command warns but does not abort —
    services may still start successfully even with partial install failures.
    """
    to_install = [
        (svc, _PALETTE[i % len(_PALETTE)])
        for i, svc in enumerate(services)
        if needs_install(svc)
    ]
    if not to_install:
        return

    print(f"{BOLD}Installing dependencies...{RESET}\n")
    for svc, color in to_install:
        exit_code = run_install(svc, color=color)
        if exit_code != 0:
            print(
                f"{YELLOW}⚠  install_cmd for '{svc.name}' exited {exit_code} "
                f"— continuing anyway{RESET}"
            )
    print()
```

- [ ] **Step 4.2: Call `_run_install_phase()` in `main()` after services are loaded**

In `main()`, insert the install phase call immediately after services are loaded and confirmed, just before `services = _resolve_services(services)`:

```python
    # Run install phase before resolving ports or starting services
    _run_install_phase(services)

    services = _resolve_services(services)
```

The diff in context (around line 123 of cli.py):
```python
    # was:
    services = _resolve_services(services)

    # becomes:
    _run_install_phase(services)
    services = _resolve_services(services)
```

- [ ] **Step 4.3: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 4.4: Manual verification — simulate fresh project**

```bash
cd /tmp
mkdir -p test-devmux-install/frontend test-devmux-install/api
# Frontend: package.json without node_modules
echo '{"scripts":{"dev":"echo frontend running"}}' > test-devmux-install/frontend/package.json
touch test-devmux-install/frontend/vite.config.ts
# Backend: requirements.txt without venv
echo "fastapi" > test-devmux-install/api/requirements.txt
echo "from fastapi import FastAPI; app = FastAPI()" > test-devmux-install/api/main.py
cd test-devmux-install
devmux
```

Expected output before starting services:
```
No dev.toml found — running auto-discovery...
  ...

Installing dependencies...
[INSTALL:WEB] npm install
[INSTALL:WEB] ...npm output...
[INSTALL:API] pip install -r requirements.txt
[INSTALL:API] ...pip output...
```

- [ ] **Step 4.5: Commit**

```bash
git add src/devmux/cli.py
git commit -m "feat: run dependency install phase before starting services"
```

---

## Task 5: Final verification

- [ ] **Step 5.1: Run full test suite**

```bash
cd /Users/ayushj/My-Github/devmux
python -m pytest tests/ -v --tb=short
```

Expected: all tests PASS, no warnings

- [ ] **Step 5.2: Verify dev.toml roundtrip includes install_cmd**

```bash
python -c "
from devmux.config import Service
from devmux.discovery import services_to_toml
svcs = [
    Service(name='web', cmd='npm run dev', port=5173, cwd='frontend', install_cmd='npm install'),
    Service(name='api', cmd='uvicorn main:app --reload', port=8000, cwd='api', install_cmd='pip install -r requirements.txt'),
]
print(services_to_toml(svcs))
"
```

Expected: TOML output contains `install_cmd` lines for both services.

- [ ] **Step 5.3: Test on the claude-code-karma worktree**

```bash
cd /Users/ayushj/My-Github/claude-code-karma/.worktrees/feature-one-command-start
# Remove node_modules if present to test detection
# rm -rf frontend/node_modules
devmux
```

Expected: install phase runs for frontend (npm install), then both services start.

- [ ] **Step 5.4: Final commit**

```bash
git add -A
git commit -m "chore: auto-install feature complete — all tests pass"
```
