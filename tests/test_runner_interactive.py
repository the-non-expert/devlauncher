"""Tests for pure runner helpers added for interactive keypress feature."""
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
