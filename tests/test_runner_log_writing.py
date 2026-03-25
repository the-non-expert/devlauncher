"""Tests for runner log file writing added for agent awareness."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _make_state(label, port=8000, pid=1234):
    from devlauncher.runner import ServiceState
    proc = MagicMock()
    proc.pid = pid
    proc.poll.return_value = None
    return ServiceState(proc=proc, label=label, color="", port=port, start_time=0.0)


# ── _open_log_files / _close_log_files ────────────────────────────────────────

def test_open_log_files_creates_dir_and_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from devlauncher.runner import _LOG_DIR, _close_log_files, _log_files, _open_log_files
    state = _make_state("API")
    _open_log_files([state])
    assert "API" in _log_files
    assert (tmp_path / _LOG_DIR / "api.log").exists()
    _close_log_files()


def test_open_log_files_multiple_services(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from devlauncher.runner import _LOG_DIR, _close_log_files, _log_files, _open_log_files
    states = [_make_state("API"), _make_state("WEB", port=5173)]
    _open_log_files(states)
    assert "API" in _log_files
    assert "WEB" in _log_files
    assert (tmp_path / _LOG_DIR / "web.log").exists()
    _close_log_files()


def test_close_log_files_clears_dict(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from devlauncher.runner import _close_log_files, _log_files, _open_log_files
    state = _make_state("API")
    _open_log_files([state])
    assert len(_log_files) > 0
    _close_log_files()
    assert len(_log_files) == 0


# ── _stream writes to log file ────────────────────────────────────────────────

def test_stream_writes_lines_to_log_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from devlauncher.runner import _LOG_DIR, _log_files, _set_filter, _stream

    _set_filter(None)
    log_dir = tmp_path / _LOG_DIR
    log_dir.mkdir()
    log_path = log_dir / "api.log"
    f = open(log_path, "w", encoding="utf-8")
    _log_files["API"] = f

    proc = MagicMock()
    proc.stdout = iter(["INFO: started\n", "INFO: ready\n"])
    _stream(proc, "API", "")

    f.close()
    _log_files.pop("API", None)

    lines = log_path.read_text().splitlines()
    assert "INFO: started" in lines
    assert "INFO: ready" in lines


def test_stream_writes_to_log_even_when_filtered_out(tmp_path, monkeypatch):
    """Log file receives all lines regardless of the active terminal filter."""
    monkeypatch.chdir(tmp_path)
    from devlauncher.runner import _LOG_DIR, _log_files, _set_filter, _stream

    _set_filter("WEB")  # terminal filter hides API output
    log_dir = tmp_path / _LOG_DIR
    log_dir.mkdir()
    log_path = log_dir / "api.log"
    f = open(log_path, "w", encoding="utf-8")
    _log_files["API"] = f

    proc = MagicMock()
    proc.stdout = iter(["API log line\n"])
    _stream(proc, "API", "")

    f.close()
    _log_files.pop("API", None)
    _set_filter(None)

    assert "API log line" in log_path.read_text()


def test_stream_skips_empty_lines(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from devlauncher.runner import _LOG_DIR, _log_files, _set_filter, _stream

    _set_filter(None)
    log_dir = tmp_path / _LOG_DIR
    log_dir.mkdir()
    log_path = log_dir / "api.log"
    f = open(log_path, "w", encoding="utf-8")
    _log_files["API"] = f

    proc = MagicMock()
    proc.stdout = iter(["real line\n", "   \n", "\n", "another line\n"])
    _stream(proc, "API", "")

    f.close()
    _log_files.pop("API", None)

    lines = [l for l in log_path.read_text().splitlines() if l]
    assert lines == ["real line", "another line"]
