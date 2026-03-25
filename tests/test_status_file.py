"""Tests for status_file: write/read/delete .devlauncher.json."""
import json
from unittest.mock import MagicMock

import pytest


def _make_state(label, port, pid, running=True):
    from devlauncher.runner import ServiceState
    proc = MagicMock()
    proc.pid = pid
    proc.poll.return_value = None if running else 1
    return ServiceState(proc=proc, label=label, color="", port=port, start_time=0.0)


def test_write_status_creates_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from devlauncher.status_file import STATUS_FILE, write_status
    state = _make_state("API", 8000, 1234)
    write_status("0.2.0", 9999, [state])
    data = json.loads((tmp_path / STATUS_FILE).read_text())
    assert data["version"] == "0.2.0"
    assert data["pid"] == 9999
    assert data["services"]["api"]["port"] == 8000
    assert data["services"]["api"]["pid"] == 1234
    assert data["services"]["api"]["status"] == "running"


def test_write_status_multiple_services(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from devlauncher.status_file import STATUS_FILE, write_status
    states = [_make_state("API", 8000, 100), _make_state("WEB", 5173, 200)]
    write_status("0.2.0", 9999, states)
    data = json.loads((tmp_path / STATUS_FILE).read_text())
    assert "api" in data["services"]
    assert "web" in data["services"]
    assert data["services"]["web"]["port"] == 5173


def test_write_status_crashed_service(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from devlauncher.status_file import STATUS_FILE, write_status
    state = _make_state("API", 8000, 1234, running=False)
    write_status("0.2.0", 9999, [state])
    data = json.loads((tmp_path / STATUS_FILE).read_text())
    assert "exited" in data["services"]["api"]["status"]


def test_write_status_label_lowercased(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from devlauncher.status_file import STATUS_FILE, write_status
    state = _make_state("MYSERVICE", 3000, 42)
    write_status("0.2.0", 1, [state])
    data = json.loads((tmp_path / STATUS_FILE).read_text())
    assert "myservice" in data["services"]


def test_read_status_returns_data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from devlauncher.status_file import read_status, write_status
    state = _make_state("WEB", 5173, 5678)
    write_status("0.2.0", 1111, [state])
    result = read_status()
    assert result is not None
    assert result["services"]["web"]["port"] == 5173


def test_read_status_missing_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from devlauncher.status_file import read_status
    assert read_status() is None


def test_read_status_invalid_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from devlauncher.status_file import STATUS_FILE, read_status
    (tmp_path / STATUS_FILE).write_text("not valid json")
    assert read_status() is None


def test_delete_status_removes_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from devlauncher.status_file import STATUS_FILE, delete_status, write_status
    state = _make_state("API", 8000, 1234)
    write_status("0.2.0", 1111, [state])
    assert (tmp_path / STATUS_FILE).exists()
    delete_status()
    assert not (tmp_path / STATUS_FILE).exists()


def test_delete_status_noop_if_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from devlauncher.status_file import delete_status
    delete_status()  # must not raise
