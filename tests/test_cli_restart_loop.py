"""Tests for the restart loop in cli.py."""
from unittest.mock import patch
import pytest


def _make_services():
    from devlauncher.config import Service
    return [Service(name="api", cmd="uvicorn main:app", port=8000)]


def test_quit_action_exits_immediately():
    services = _make_services()
    with patch("devlauncher.cli.run_services", return_value="quit") as mock_run, \
         patch("devlauncher.cli._run_install_phase"), \
         patch("devlauncher.cli._resolve_services", return_value=services):
        from devlauncher.cli import _restart_loop
        with pytest.raises(SystemExit):
            _restart_loop(services, services)
    mock_run.assert_called_once()


def test_soft_restart_does_not_reinstall():
    services = _make_services()
    run_calls = iter(["soft_restart", "quit"])
    with patch("devlauncher.cli.run_services", side_effect=run_calls) as mock_run, \
         patch("devlauncher.cli._run_install_phase") as mock_install, \
         patch("devlauncher.cli._resolve_services", return_value=services):
        from devlauncher.cli import _restart_loop
        with pytest.raises(SystemExit):
            _restart_loop(services, services)
    assert mock_run.call_count == 2
    mock_install.assert_not_called()


def test_hard_restart_reinstalls_and_reruns():
    services = _make_services()
    run_calls = iter(["hard_restart", "quit"])
    with patch("devlauncher.cli.run_services", side_effect=run_calls) as mock_run, \
         patch("devlauncher.cli._run_install_phase") as mock_install, \
         patch("devlauncher.cli._resolve_services", return_value=services):
        from devlauncher.cli import _restart_loop
        with pytest.raises(SystemExit):
            _restart_loop(services, services)
    assert mock_run.call_count == 2
    mock_install.assert_called_once()


def test_hard_restart_re_resolves_ports():
    services = _make_services()
    run_calls = iter(["hard_restart", "quit"])
    with patch("devlauncher.cli.run_services", side_effect=run_calls), \
         patch("devlauncher.cli._run_install_phase"), \
         patch("devlauncher.cli._resolve_services", return_value=services) as mock_resolve:
        from devlauncher.cli import _restart_loop
        with pytest.raises(SystemExit):
            _restart_loop(services, services)
    # Called once inside _restart_loop during the hard restart branch.
    assert mock_resolve.call_count == 1
