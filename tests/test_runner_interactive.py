"""Tests for pure runner helpers added for interactive keypress feature."""
import sys
import pytest


def test_format_uptime_under_a_minute():
    from devlauncher.runner import _format_uptime
    assert _format_uptime(0) == "0s"
    assert _format_uptime(1) == "1s"
    assert _format_uptime(59) == "59s"


def test_format_uptime_minutes():
    from devlauncher.runner import _format_uptime
    assert _format_uptime(60) == "1m 0s"
    assert _format_uptime(90) == "1m 30s"
    assert _format_uptime(3599) == "59m 59s"


def test_format_uptime_hours():
    from devlauncher.runner import _format_uptime
    assert _format_uptime(3600) == "1h 0m"
    assert _format_uptime(7384) == "2h 3m"


def test_cycle_log_filter_none_to_first():
    from devlauncher.runner import _cycle_log_filter, _get_filter, _set_filter
    _set_filter(None)
    _cycle_log_filter(["API", "WEB"])
    assert _get_filter() == "API"


def test_cycle_log_filter_wraps_to_next():
    from devlauncher.runner import _cycle_log_filter, _get_filter, _set_filter
    _set_filter("API")
    _cycle_log_filter(["API", "WEB"])
    assert _get_filter() == "WEB"


def test_cycle_log_filter_wraps_to_none():
    from devlauncher.runner import _cycle_log_filter, _get_filter, _set_filter
    _set_filter("WEB")
    _cycle_log_filter(["API", "WEB"])
    assert _get_filter() is None


def test_cycle_log_filter_single_service_wraps():
    from devlauncher.runner import _cycle_log_filter, _get_filter, _set_filter
    _set_filter(None)
    _cycle_log_filter(["API"])
    assert _get_filter() == "API"
    _cycle_log_filter(["API"])
    assert _get_filter() is None


# ── _kill_all ──────────────────────────────────────────────────────────────────

def _make_state(terminated_quickly: bool):
    from unittest.mock import MagicMock
    from devlauncher.runner import ServiceState
    proc = MagicMock()
    proc.poll.return_value = None
    if terminated_quickly:
        proc.wait.return_value = 0
    else:
        import subprocess
        proc.wait.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=5)
    return ServiceState(proc=proc, label="API", color="", port=8000, start_time=0.0)


@pytest.mark.skipif(sys.platform == "win32", reason="os.getpgid/killpg are POSIX-only")
def test_kill_all_terminates_running_procs():
    from unittest.mock import patch
    from devlauncher.runner import _kill_all
    state = _make_state(terminated_quickly=True)
    state.proc.pid = 1234
    with patch("devlauncher.runner.os.getpgid", return_value=1234), \
         patch("devlauncher.runner.os.killpg") as mock_killpg:
        _kill_all([state])
    mock_killpg.assert_called()


@pytest.mark.skipif(sys.platform == "win32", reason="os.getpgid/killpg are POSIX-only")
def test_kill_all_force_kills_on_timeout():
    import signal
    from unittest.mock import patch, call
    from devlauncher.runner import _kill_all
    state = _make_state(terminated_quickly=False)
    state.proc.pid = 1234
    with patch("devlauncher.runner.os.getpgid", return_value=1234), \
         patch("devlauncher.runner.os.killpg") as mock_killpg:
        _kill_all([state])
    calls = [c[0][1] for c in mock_killpg.call_args_list]
    assert signal.SIGTERM in calls
    assert signal.SIGKILL in calls


def test_kill_all_empty_list_is_noop():
    from devlauncher.runner import _kill_all
    _kill_all([])


# ── _print_status ──────────────────────────────────────────────────────────────

def test_print_status_shows_all_services(capsys):
    from unittest.mock import MagicMock
    from devlauncher.runner import ServiceState, _print_status
    proc = MagicMock()
    proc.pid = 42
    proc.poll.return_value = None
    state = ServiceState(proc=proc, label="API", color="", port=8000, start_time=0.0)
    _print_status([state])
    out = capsys.readouterr().out
    assert "API" in out
    assert "8000" in out
    assert "42" in out


def test_print_status_shows_crashed_service(capsys):
    from unittest.mock import MagicMock
    from devlauncher.runner import ServiceState, _print_status
    proc = MagicMock()
    proc.pid = 99
    proc.poll.return_value = 1
    state = ServiceState(proc=proc, label="WEB", color="", port=5173, start_time=0.0)
    _print_status([state])
    out = capsys.readouterr().out
    assert "crashed" in out.lower() or "exited" in out.lower()
