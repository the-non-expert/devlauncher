"""Tests for dev.toml schema migration (migration.py)."""

import textwrap
from pathlib import Path

import pytest

from devlauncher.config import Service
from devlauncher.migration import (
    CURRENT_SCHEMA_VERSION,
    check_and_migrate,
    read_schema_version,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _write_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "dev.toml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def _make_service(name: str, cwd: str = ".") -> Service:
    return Service(name=name, cmd="uvicorn main:app --reload", port=8000, cwd=cwd)


# ── read_schema_version ────────────────────────────────────────────────────────

def test_read_schema_version_missing(tmp_path):
    p = _write_toml(tmp_path, """\
        [services.api]
        cmd = "uvicorn main:app"
        port = 8000
    """)
    assert read_schema_version(p) == 0


def test_read_schema_version_present(tmp_path):
    p = _write_toml(tmp_path, """\
        schema_version = 1

        [services.api]
        cmd = "uvicorn main:app"
        port = 8000
    """)
    assert read_schema_version(p) == 1


def test_read_schema_version_nonexistent_file(tmp_path):
    assert read_schema_version(tmp_path / "nope.toml") == 0


# ── check_and_migrate: no migration needed ─────────────────────────────────────

def test_no_migration_when_current_schema(tmp_path):
    p = _write_toml(tmp_path, f"""\
        schema_version = {CURRENT_SCHEMA_VERSION}

        [services.api]
        cmd = "uvicorn main:app"
        port = 8000
        cwd = "backend"
    """)
    svc = Service(name="api", cmd="uvicorn main:app", port=8000, cwd="backend")
    updated, changelog = check_and_migrate(p, [svc])
    assert changelog == []
    assert updated[0].cwd == "backend"


# ── check_and_migrate: v0 → v1 ────────────────────────────────────────────────

def test_migration_updates_cwd_when_discovery_matches(tmp_path, monkeypatch):
    """When discovery returns a service with a non-root cwd, migration applies it."""
    p = _write_toml(tmp_path, """\
        [services.api]
        cmd = "uvicorn main:app --reload"
        port = 8000
    """)
    svc = _make_service("api", cwd=".")

    discovered = Service(name="api", cmd="uvicorn main:app --reload", port=8000, cwd="backend")

    import devlauncher.migration as mig
    monkeypatch.setattr(mig, "_migrate_v0_to_v1", lambda path, svcs: (
        [Service(name=s.name, cmd=s.cmd, port=s.port, cwd="backend" if s.name == "api" else s.cwd)
         for s in svcs],
        ["  [api] cwd: '.' → 'backend'  (auto-detected)"],
    ))

    updated, changelog = check_and_migrate(p, [svc])

    assert len(changelog) == 1
    assert "backend" in changelog[0]
    assert updated[0].cwd == "backend"
    # dev.toml should now have schema_version = 1
    assert "schema_version = 1" in p.read_text()


def test_migration_does_not_overwrite_explicit_cwd(tmp_path, monkeypatch):
    """Services with a user-set cwd (not '.') are left untouched."""
    p = _write_toml(tmp_path, """\
        [services.api]
        cmd = "uvicorn main:app --reload"
        port = 8000
        cwd = "src/api"
    """)
    svc = Service(name="api", cmd="uvicorn main:app --reload", port=8000, cwd="src/api")

    # Discovery suggests a different cwd — should NOT override user's value
    import devlauncher.discovery as disc
    monkeypatch.setattr(
        disc, "discover_services",
        lambda root=None: ([
            Service(name="api", cmd="uvicorn main:app --reload", port=8000, cwd="backend")
        ], []),
    )

    updated, changelog = check_and_migrate(p, [svc])
    assert updated[0].cwd == "src/api"  # unchanged


def test_migration_leaves_unmatched_service_unchanged(tmp_path, monkeypatch):
    """A service that discovery cannot match by name is left with its original cwd."""
    p = _write_toml(tmp_path, """\
        [services.myapp]
        cmd = "uvicorn main:app --reload"
        port = 8000
    """)
    svc = _make_service("myapp", cwd=".")

    import devlauncher.discovery as disc
    # Discovery returns nothing matching "myapp"
    monkeypatch.setattr(disc, "discover_services", lambda root=None: ([], []))

    updated, changelog = check_and_migrate(p, [svc])
    assert updated[0].cwd == "."
    assert changelog == []


def test_migration_handles_discovery_exception(tmp_path, monkeypatch):
    """If discovery raises, migration silently returns original services."""
    p = _write_toml(tmp_path, """\
        [services.api]
        cmd = "uvicorn main:app"
        port = 8000
    """)
    svc = _make_service("api")

    import devlauncher.discovery as disc
    monkeypatch.setattr(disc, "discover_services", lambda root=None: (_ for _ in ()).throw(RuntimeError("boom")))

    updated, changelog = check_and_migrate(p, [svc])
    assert updated[0].cwd == "."
    assert changelog == []


def test_migrated_toml_has_schema_version(tmp_path, monkeypatch):
    """After migration the written file contains schema_version = 1."""
    p = _write_toml(tmp_path, """\
        [services.api]
        cmd = "uvicorn main:app --reload"
        port = 8000
    """)
    svc = _make_service("api", cwd=".")

    import devlauncher.migration as mig
    monkeypatch.setattr(mig, "_migrate_v0_to_v1", lambda path, svcs: (
        [Service(name=s.name, cmd=s.cmd, port=s.port, cwd="backend") for s in svcs],
        ["  [api] cwd: '.' → 'backend'  (auto-detected)"],
    ))

    check_and_migrate(p, [svc])
    written = p.read_text()
    assert f"schema_version = {CURRENT_SCHEMA_VERSION}" in written
