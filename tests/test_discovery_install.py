"""Tests for install_cmd inference in auto-discovery."""
import json
from pathlib import Path

import pytest

from devlauncher.discovery import discover_services, services_to_toml


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
    assert svc is not None
    assert svc.install_cmd is None


# ── Bun frontend ───────────────────────────────────────────────────────────────

def test_discovers_bun_install_for_bun_project(tmp_path):
    fe = tmp_path / "frontend"
    fe.mkdir()
    _write_pkg_json(fe, deps={"vite": "^5.0.0"})
    (fe / "vite.config.ts").write_text("")
    (fe / "bun.lockb").write_text("")
    services, _ = discover_services(str(tmp_path))
    web = next((s for s in services if s.name == "web"), None)
    assert web is not None
    assert web.install_cmd == "bun install"


# ── services_to_toml includes install_cmd ─────────────────────────────────────

def test_services_to_toml_includes_install_cmd(tmp_path):
    fe = tmp_path / "frontend"
    fe.mkdir()
    _write_pkg_json(fe, deps={"vite": "^5.0.0"})
    (fe / "vite.config.ts").write_text("")
    services, _ = discover_services(str(tmp_path))
    toml = services_to_toml(services)
    assert "install_cmd" in toml
    assert "npm install" in toml
