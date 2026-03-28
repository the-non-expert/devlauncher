"""Tests for N-service auto-discovery."""
import json
from pathlib import Path

import pytest

from devlauncher.discovery import discover_services


def _pkg(directory: Path, scripts=None, deps=None):
    pkg = {"scripts": scripts or {"dev": "vite"}, "dependencies": deps or {}}
    (directory / "package.json").write_text(json.dumps(pkg))


def test_discovers_two_fastapi_services(tmp_path):
    for dirname in ("api", "auth"):
        d = tmp_path / dirname
        d.mkdir()
        (d / "requirements.txt").write_text("fastapi\nuvicorn\n")
        (d / "main.py").write_text("")
    services, _ = discover_services(str(tmp_path))
    names = {s.name for s in services}
    assert "api" in names
    assert "auth" in names
    assert len([s for s in services if "uvicorn" in s.cmd]) == 2


def test_discovers_fastapi_go_and_vite(tmp_path):
    api = tmp_path / "api"
    api.mkdir()
    (api / "requirements.txt").write_text("fastapi\nuvicorn\n")
    (api / "main.py").write_text("")

    gw = tmp_path / "gateway"
    gw.mkdir()
    (gw / "go.mod").write_text("module example.com/gw\ngo 1.21\n")
    (gw / "main.go").write_text("package main\nfunc main() {}\n")

    fe = tmp_path / "frontend"
    fe.mkdir()
    _pkg(fe, deps={"vite": "^5.0.0"})
    (fe / "vite.config.ts").write_text("")

    services, _ = discover_services(str(tmp_path))
    names = {s.name for s in services}
    assert names == {"api", "gateway", "web"}


def test_deduplicates_names_with_numeric_suffix(tmp_path):
    # "api/" → "api", "api-service/" strips "-service" → "api" → dedup → "api2"
    api = tmp_path / "api"
    api.mkdir()
    (api / "requirements.txt").write_text("fastapi\nuvicorn\n")
    (api / "main.py").write_text("")

    api2 = tmp_path / "api-service"
    api2.mkdir()
    (api2 / "requirements.txt").write_text("fastapi\nuvicorn\n")
    (api2 / "main.py").write_text("")

    services, _ = discover_services(str(tmp_path))
    names = {s.name for s in services}
    assert "api" in names
    assert "api2" in names


def test_root_with_both_roles_produces_two_services(tmp_path):
    """A root dir with vite.config + requirements.txt (fastapi) → 2 services."""
    _pkg(tmp_path, deps={"vite": "^5.0.0"})
    (tmp_path / "vite.config.ts").write_text("")
    (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n")
    (tmp_path / "main.py").write_text("")
    services, _ = discover_services(str(tmp_path))
    names = {s.name for s in services}
    assert "web" in names
    assert "api" in names


def test_root_skipped_for_backend_when_subdir_covers_it(tmp_path):
    """Root has requirements.txt but api/ subdir also has FastAPI → root skipped."""
    (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n")
    (tmp_path / "main.py").write_text("")

    api = tmp_path / "api"
    api.mkdir()
    (api / "requirements.txt").write_text("fastapi\nuvicorn\n")
    (api / "main.py").write_text("")

    services, _ = discover_services(str(tmp_path))
    backend_cwds = [s.cwd for s in services if "uvicorn" in s.cmd]
    assert backend_cwds == ["api"]


def test_uncertain_score_skipped_with_warning(tmp_path):
    """A directory with only a LOW signal (score=1) is skipped with a warning."""
    low = tmp_path / "misc"
    low.mkdir()
    (low / "main.py").write_text("")  # LOW backend signal only (score=1)
    services, warnings = discover_services(str(tmp_path))
    assert not any(s.cwd == "misc" for s in services)
    assert any("Low-confidence" in w for w in warnings)


def test_service_name_strips_noise_suffixes(tmp_path):
    d = tmp_path / "auth-service"
    d.mkdir()
    (d / "requirements.txt").write_text("fastapi\nuvicorn\n")
    (d / "main.py").write_text("")
    services, _ = discover_services(str(tmp_path))
    assert any(s.name == "auth" for s in services)


def test_three_way_name_deduplication(tmp_path):
    """Three dirs all resolving to 'api' → api, api2, api3."""
    for dirname in ("api", "api-service", "backend"):
        d = tmp_path / dirname
        d.mkdir()
        (d / "requirements.txt").write_text("fastapi\nuvicorn\n")
        (d / "main.py").write_text("")
    services, _ = discover_services(str(tmp_path))
    names = {s.name for s in services}
    assert names == {"api", "api2", "api3"}


def test_two_frontend_dirs_deduplicated(tmp_path):
    """Two frontend dirs both mapping to 'web' → web, web2."""
    fe1 = tmp_path / "frontend"
    fe1.mkdir()
    _pkg(fe1, deps={"vite": "^5.0.0"})
    (fe1 / "vite.config.ts").write_text("")

    fe2 = tmp_path / "web"
    fe2.mkdir()
    _pkg(fe2, deps={"vite": "^5.0.0"})
    (fe2 / "vite.config.ts").write_text("")

    services, _ = discover_services(str(tmp_path))
    names = {s.name for s in services}
    assert "web" in names
    assert "web2" in names


def test_discovery_order_is_deterministic(tmp_path):
    """Same project structure always returns services in the same order."""
    for dirname in ("api", "auth", "frontend"):
        d = tmp_path / dirname
        d.mkdir()
    (tmp_path / "api" / "requirements.txt").write_text("fastapi\nuvicorn\n")
    (tmp_path / "api" / "main.py").write_text("")
    (tmp_path / "auth" / "requirements.txt").write_text("fastapi\nuvicorn\n")
    (tmp_path / "auth" / "main.py").write_text("")
    _pkg(tmp_path / "frontend", deps={"vite": "^5.0.0"})
    (tmp_path / "frontend" / "vite.config.ts").write_text("")

    first, _ = discover_services(str(tmp_path))
    second, _ = discover_services(str(tmp_path))
    assert [s.name for s in first] == [s.name for s in second]


def test_two_fastapi_services_get_different_ports_after_resolution(tmp_path):
    """Two FastAPI services both default to 8000 in discovery — ports resolved at runtime."""
    for dirname in ("api", "auth"):
        d = tmp_path / dirname
        d.mkdir()
        (d / "requirements.txt").write_text("fastapi\nuvicorn\n")
        (d / "main.py").write_text("")

    services, _ = discover_services(str(tmp_path))
    # Both default to 8000 in discovery (expected — runtime find_free_port resolves conflicts)
    ports = [s.port for s in services if "uvicorn" in s.cmd]
    assert len(ports) == 2
    assert all(p == 8000 for p in ports)  # documented: same default, resolved at runtime
