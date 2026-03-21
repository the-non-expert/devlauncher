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
