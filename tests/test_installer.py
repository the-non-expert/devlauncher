"""Tests for dependency detection and install execution."""
import os
import sys
import time

import pytest

from devlauncher.config import Service
from devlauncher.installer import needs_install, run_install


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
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    lock = tmp_path / "package-lock.json"
    lock.write_text("{}")
    # Force lock file mtime to be strictly in the future
    future = time.time() + 1
    os.utime(lock, (future, future))
    svc = _svc(str(tmp_path), "npm install")
    assert needs_install(svc) is True


def test_needs_install_node_fresh_lock_file(tmp_path):
    """Lock file older than node_modules → no install needed."""
    lock = tmp_path / "package-lock.json"
    lock.write_text("{}")
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    # Force lock file mtime to be in the past
    past = time.time() - 1
    os.utime(lock, (past, past))
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

def test_run_install_returns_zero_when_no_install_cmd(tmp_path):
    svc = Service(name="api", cmd="uvicorn main:app", port=8000,
                  cwd=str(tmp_path))
    exit_code = run_install(svc, color="\033[94m")
    assert exit_code == 0


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
