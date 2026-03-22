"""Tests for Service.install_cmd parsing and serialization."""
import textwrap
import pytest
from devlauncher.config import Service, load_config
from devlauncher.discovery import services_to_toml


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
