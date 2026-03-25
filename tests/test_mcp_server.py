"""Tests for mcp_server: devlauncher_status, devlauncher_logs, ensure_registered."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest


# ── devlauncher_status ────────────────────────────────────────────────────────

def test_status_returns_data_when_running(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    payload = {
        "version": "0.2.0",
        "pid": 1234,
        "services": {"api": {"port": 8000, "pid": 100, "status": "running"}},
    }
    (tmp_path / ".devlauncher.json").write_text(json.dumps(payload))
    from devlauncher.mcp_server import devlauncher_status
    result = devlauncher_status()
    assert result["pid"] == 1234
    assert result["services"]["api"]["port"] == 8000


def test_status_returns_not_running_when_no_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from devlauncher.mcp_server import devlauncher_status
    result = devlauncher_status()
    assert result == {"running": False}


def test_status_returns_not_running_on_invalid_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".devlauncher.json").write_text("corrupted")
    from devlauncher.mcp_server import devlauncher_status
    result = devlauncher_status()
    assert result == {"running": False}


# ── devlauncher_logs ──────────────────────────────────────────────────────────

def test_logs_returns_last_n_lines(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    log_dir = tmp_path / ".devlauncher-logs"
    log_dir.mkdir()
    (log_dir / "api.log").write_text("line1\nline2\nline3\n")
    from devlauncher.mcp_server import devlauncher_logs
    result = devlauncher_logs("api", 2)
    assert result["service"] == "api"
    assert result["lines"] == ["line2", "line3"]
    assert result["total_available"] == 3


def test_logs_returns_all_when_fewer_than_requested(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    log_dir = tmp_path / ".devlauncher-logs"
    log_dir.mkdir()
    (log_dir / "web.log").write_text("only one line\n")
    from devlauncher.mcp_server import devlauncher_logs
    result = devlauncher_logs("web", 50)
    assert result["lines"] == ["only one line"]
    assert result["total_available"] == 1


def test_logs_missing_service_returns_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from devlauncher.mcp_server import devlauncher_logs
    result = devlauncher_logs("nonexistent", 10)
    assert result["lines"] == []
    assert result["total_available"] == 0
    assert result["service"] == "nonexistent"


def test_logs_caps_lines_at_500(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    log_dir = tmp_path / ".devlauncher-logs"
    log_dir.mkdir()
    (log_dir / "api.log").write_text("\n".join(f"line{i}" for i in range(600)) + "\n")
    from devlauncher.mcp_server import devlauncher_logs
    result = devlauncher_logs("api", 1000)  # request more than cap
    assert len(result["lines"]) == 500


def test_logs_service_name_case_insensitive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    log_dir = tmp_path / ".devlauncher-logs"
    log_dir.mkdir()
    (log_dir / "api.log").write_text("hello\n")
    from devlauncher.mcp_server import devlauncher_logs
    result = devlauncher_logs("API", 10)  # uppercase service name
    assert result["lines"] == ["hello"]


def test_logs_default_lines_is_50(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    log_dir = tmp_path / ".devlauncher-logs"
    log_dir.mkdir()
    content = "\n".join(f"line{i}" for i in range(100)) + "\n"
    (log_dir / "api.log").write_text(content)
    from devlauncher.mcp_server import devlauncher_logs
    result = devlauncher_logs("api")
    assert len(result["lines"]) == 50


# ── ensure_registered ─────────────────────────────────────────────────────────

def test_ensure_registered_creates_settings_file(tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    with patch("devlauncher.mcp_server._CLAUDE_SETTINGS", settings_path), \
         patch("devlauncher.mcp_server._mcp_command", return_value="/usr/local/bin/devlauncher-mcp"):
        from devlauncher.mcp_server import ensure_registered
        ensure_registered()
    data = json.loads(settings_path.read_text())
    assert "devlauncher" in data["mcpServers"]
    assert data["mcpServers"]["devlauncher"]["command"] == "/usr/local/bin/devlauncher-mcp"


def test_ensure_registered_uses_absolute_path(tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    with patch("devlauncher.mcp_server._CLAUDE_SETTINGS", settings_path), \
         patch("devlauncher.mcp_server._mcp_command", return_value="/some/bin/devlauncher-mcp"):
        from devlauncher.mcp_server import ensure_registered
        ensure_registered()
    data = json.loads(settings_path.read_text())
    cmd = data["mcpServers"]["devlauncher"]["command"]
    assert cmd == "/some/bin/devlauncher-mcp"


def test_ensure_registered_idempotent(tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps({"mcpServers": {"devlauncher": {"command": "/usr/local/bin/devlauncher-mcp"}}})
    )
    with patch("devlauncher.mcp_server._CLAUDE_SETTINGS", settings_path), \
         patch("devlauncher.mcp_server._mcp_command", return_value="/usr/local/bin/devlauncher-mcp"):
        from devlauncher.mcp_server import ensure_registered
        ensure_registered()
        ensure_registered()
    data = json.loads(settings_path.read_text())
    assert list(data["mcpServers"].keys()) == ["devlauncher"]  # no duplicates


def test_ensure_registered_preserves_existing_keys(tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps({"theme": "dark", "mcpServers": {"other": {"command": "other-cmd"}}})
    )
    with patch("devlauncher.mcp_server._CLAUDE_SETTINGS", settings_path), \
         patch("devlauncher.mcp_server._mcp_command", return_value="/usr/bin/devlauncher-mcp"):
        from devlauncher.mcp_server import ensure_registered
        ensure_registered()
    data = json.loads(settings_path.read_text())
    assert data["theme"] == "dark"
    assert "other" in data["mcpServers"]
    assert "devlauncher" in data["mcpServers"]


def test_ensure_registered_creates_mcp_servers_key(tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({"theme": "dark"}))  # no mcpServers key
    with patch("devlauncher.mcp_server._CLAUDE_SETTINGS", settings_path), \
         patch("devlauncher.mcp_server._mcp_command", return_value="/usr/bin/devlauncher-mcp"):
        from devlauncher.mcp_server import ensure_registered
        ensure_registered()
    data = json.loads(settings_path.read_text())
    assert "mcpServers" in data
    assert "devlauncher" in data["mcpServers"]


def test_status_live_checks_pid_on_crash(tmp_path, monkeypatch):
    """devlauncher_status() must detect crashed services via live PID check."""
    monkeypatch.chdir(tmp_path)
    payload = {
        "version": "0.2.0",
        "pid": 1234,
        "services": {"api": {"port": 8000, "pid": 99999, "status": "running"}},
    }
    (tmp_path / ".devlauncher.json").write_text(json.dumps(payload))

    import devlauncher.mcp_server as mcp_mod
    # Simulate a dead PID by making os.kill raise ProcessLookupError
    original_kill = mcp_mod.os.kill
    def fake_kill(pid, sig):
        raise ProcessLookupError
    monkeypatch.setattr(mcp_mod.os, "kill", fake_kill)

    from devlauncher.mcp_server import devlauncher_status
    result = devlauncher_status()
    assert result["services"]["api"]["status"] == "crashed"


def test_status_live_checks_pid_still_running(tmp_path, monkeypatch):
    """devlauncher_status() keeps 'running' when PID is alive."""
    monkeypatch.chdir(tmp_path)
    payload = {
        "version": "0.2.0",
        "pid": 1234,
        "services": {"api": {"port": 8000, "pid": 99999, "status": "running"}},
    }
    (tmp_path / ".devlauncher.json").write_text(json.dumps(payload))

    import devlauncher.mcp_server as mcp_mod
    monkeypatch.setattr(mcp_mod.os, "kill", lambda pid, sig: None)  # alive

    from devlauncher.mcp_server import devlauncher_status
    result = devlauncher_status()
    assert result["services"]["api"]["status"] == "running"


def test_ensure_registered_handles_corrupt_settings(tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text("not json at all")
    with patch("devlauncher.mcp_server._CLAUDE_SETTINGS", settings_path), \
         patch("devlauncher.mcp_server._mcp_command", return_value="/usr/bin/devlauncher-mcp"):
        from devlauncher.mcp_server import ensure_registered
        ensure_registered()  # must not raise
    data = json.loads(settings_path.read_text())
    assert "devlauncher" in data["mcpServers"]
