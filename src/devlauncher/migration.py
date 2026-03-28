"""Dev.toml schema migration.

Detects outdated dev.toml files and applies forward migrations automatically
on every devlauncher run. Migrations only add missing fields — existing user
customisations (ports, commands, env vars) are never overwritten.

Schema versions:
  0 (legacy): No schema_version field. Services may be missing 'cwd'.
  1 (current): schema_version = 1. All services have explicit 'cwd'.
"""

import re
from dataclasses import replace
from pathlib import Path
from typing import List, Tuple

from .config import Service
from .discovery import CURRENT_SCHEMA_VERSION, services_to_toml


def read_schema_version(path: Path) -> int:
    """Read schema_version from a dev.toml file. Returns 0 if not present."""
    try:
        text = path.read_text(encoding="utf-8")
        match = re.search(r"^schema_version\s*=\s*(\d+)", text, re.MULTILINE)
        if match:
            return int(match.group(1))
    except OSError:
        pass
    return 0


def check_and_migrate(
    config_path: Path,
    services: List[Service],
) -> Tuple[List[Service], List[str]]:
    """Migrate dev.toml to the current schema version if needed.

    Args:
        config_path: Path to the dev.toml file.
        services:    Services already loaded from that file.

    Returns:
        (services, changelog) — updated service list and human-readable
        description of what changed. changelog is empty if no migration
        was needed. On any error the original services are returned unchanged.
    """
    schema_version = read_schema_version(config_path)
    if schema_version >= CURRENT_SCHEMA_VERSION:
        return services, []

    updated = list(services)
    changelog: List[str] = []

    if schema_version < 1:
        updated, v1_changes = _migrate_v0_to_v1(config_path, updated)
        changelog.extend(v1_changes)

    if changelog:
        try:
            config_path.write_text(services_to_toml(updated), encoding="utf-8")
        except OSError as exc:
            # Write failure is non-fatal — continue with in-memory update.
            changelog.append(f"  ⚠  Could not write updated dev.toml: {exc}")

    return updated, changelog


def _migrate_v0_to_v1(
    config_path: Path,
    services: List[Service],
) -> Tuple[List[Service], List[str]]:
    """Migration v0 → v1: infer and add missing cwd fields.

    Re-runs auto-discovery on the project root, then matches discovered
    services to existing ones by name. If a discovered service has a
    non-root cwd and the existing service still has cwd='.', the existing
    entry is updated.

    Services that cannot be matched are left untouched.
    """
    from .discovery import discover_services

    try:
        discovered, _ = discover_services(str(config_path.parent))
    except Exception:
        return services, []

    discovered_by_name = {s.name: s for s in discovered}
    updated: List[Service] = []
    changes: List[str] = []

    for svc in services:
        disc = discovered_by_name.get(svc.name)
        if disc and svc.cwd == "." and disc.cwd != ".":
            updated.append(replace(svc, cwd=disc.cwd))
            changes.append(f"  [{svc.name}] cwd: '.' → '{disc.cwd}'  (auto-detected)")
        else:
            updated.append(svc)

    return updated, changes
