# tests/test_cli_init.py
"""Tests for the `devlauncher init` subcommand."""
from unittest.mock import patch
import pytest

from devlauncher.config import Service


def _make_services():
    return [
        Service(name="api", cmd="uvicorn main:app --reload --port {self.port}", port=8000, cwd="api"),
        Service(name="web", cmd="npm run dev -- --port {self.port}", port=5173, cwd="frontend"),
    ]


def test_init_writes_dev_toml_when_confirmed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    services = _make_services()
    with patch("devlauncher.cli.discover_services", return_value=(services, [])), \
         patch("builtins.input", return_value="y"):
        from devlauncher.cli import _run_init
        _run_init()
    assert (tmp_path / "dev.toml").exists()
    content = (tmp_path / "dev.toml").read_text()
    assert "[services.api]" in content
    assert "[services.web]" in content


def test_init_does_not_write_when_declined(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    services = _make_services()
    with patch("devlauncher.cli.discover_services", return_value=(services, [])), \
         patch("builtins.input", return_value="n"):
        from devlauncher.cli import _run_init
        with pytest.raises(SystemExit) as exc:
            _run_init()
        assert exc.value.code == 0
    assert not (tmp_path / "dev.toml").exists()


def test_init_exits_with_1_when_no_services_detected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch("devlauncher.cli.discover_services", return_value=([], [])):
        from devlauncher.cli import _run_init
        with pytest.raises(SystemExit) as exc:
            _run_init()
        assert exc.value.code == 1


def test_init_prompts_overwrite_when_dev_toml_exists(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dev.toml").write_text("# existing", encoding="utf-8")
    services = _make_services()
    with patch("devlauncher.cli.discover_services", return_value=(services, [])), \
         patch("builtins.input", return_value="y"):
        from devlauncher.cli import _run_init
        _run_init()
    content = (tmp_path / "dev.toml").read_text()
    assert "[services.api]" in content  # overwritten


def test_init_does_not_overwrite_when_declined(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    original = "# original content"
    (tmp_path / "dev.toml").write_text(original, encoding="utf-8")
    services = _make_services()
    with patch("devlauncher.cli.discover_services", return_value=(services, [])), \
         patch("builtins.input", return_value="n"):
        from devlauncher.cli import _run_init
        with pytest.raises(SystemExit) as exc:
            _run_init()
        assert exc.value.code == 0
    assert (tmp_path / "dev.toml").read_text() == original


def test_init_prints_warnings(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    services = _make_services()
    warnings = ["Multiple frontend candidates found: 'web' and 'client'."]
    with patch("devlauncher.cli.discover_services", return_value=(services, warnings)), \
         patch("builtins.input", return_value="n"):
        from devlauncher.cli import _run_init
        with pytest.raises(SystemExit):
            _run_init()
    captured = capsys.readouterr()
    assert "Multiple frontend candidates" in captured.out


def test_init_default_yes_on_empty_input(tmp_path, monkeypatch):
    """Pressing Enter (empty input) accepts the default Y."""
    monkeypatch.chdir(tmp_path)
    services = _make_services()
    with patch("devlauncher.cli.discover_services", return_value=(services, [])), \
         patch("builtins.input", return_value=""):
        from devlauncher.cli import _run_init
        _run_init()
    assert (tmp_path / "dev.toml").exists()


def test_init_subcommand_routes_correctly():
    """sys.argv == ['devlauncher', 'init'] calls _run_init, not run_services."""
    with patch("sys.argv", ["devlauncher", "init"]), \
         patch("devlauncher.cli._run_init") as mock_init, \
         patch("devlauncher.mcp_server.ensure_registered"):
        from devlauncher.cli import main
        main()
    mock_init.assert_called_once()
