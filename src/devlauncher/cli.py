"""devlauncher CLI entry point.

Usage:
    devlauncher               # reads dev.toml, or auto-discovers services
    devlauncher path/to/dev.toml
    python -m devlauncher
"""

import sys
from dataclasses import replace
from pathlib import Path
from typing import List

from .config import Service, load_config, resolve_port_refs
from .discovery import discover_services, services_to_toml
from .installer import needs_install, run_install
from .ports import find_free_port
from .runner import BOLD, RESET, YELLOW, _PALETTE, run_services


def _run_install_phase(services: List[Service]) -> None:
    """Run dependency installs for any service that needs them.

    Installs run sequentially (not in parallel) so output stays readable.
    A non-zero exit code from an install command warns but does not abort —
    services may still start successfully even with partial install failures.
    """
    needs = [svc for svc in services if needs_install(svc)]
    to_install = [
        (svc, _PALETTE[i % len(_PALETTE)])
        for i, svc in enumerate(needs)
    ]
    if not to_install:
        return

    print(f"{BOLD}Installing dependencies...{RESET}\n")
    for svc, color in to_install:
        exit_code = run_install(svc, color=color)
        if exit_code != 0:
            print(
                f"{YELLOW}⚠  install_cmd for '{svc.name}' exited {exit_code} "
                f"— continuing anyway{RESET}"
            )
    print()


def _resolve_services(services: List[Service]) -> List[Service]:
    """Detect port conflicts, notify user, return services with actual ports."""
    resolved_ports: dict[str, int] = {}
    final: List[Service] = []

    for svc in services:
        actual = find_free_port(svc.port)
        resolved_ports[svc.name] = actual
        if actual != svc.port:
            print(
                f"{YELLOW}⚠  Port {svc.port} in use → using {actual} "
                f"for {svc.name}{RESET}"
            )
        final.append(replace(svc, port=actual))

    # Resolve {name.port} and {self.port} references now that all ports are known
    return resolve_port_refs(final, resolved_ports)


def main() -> None:
    explicit_config = len(sys.argv) > 1
    config_path = sys.argv[1] if explicit_config else "dev.toml"

    services: List[Service] = []

    if Path(config_path).exists():
        # dev.toml present — use it
        try:
            services = load_config(config_path)
        except (ValueError, Exception) as e:
            print(f"Config error: {e}", file=sys.stderr)
            sys.exit(1)

    elif explicit_config:
        # User passed a path that doesn't exist
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    else:
        # No dev.toml — run auto-discovery once, confirm, then save
        print(f"{YELLOW}No dev.toml found — running auto-discovery...{RESET}\n")
        services, warnings = discover_services()

        for w in warnings:
            print(f"{YELLOW}⚠  {w}{RESET}")

        if not services:
            print(
                "\nNo services detected. Create a dev.toml to define your services.\n"
                "  Example:\n"
                "    [services.api]\n"
                '    cmd = "uvicorn main:app --reload --port {self.port}"\n'
                "    port = 8000\n"
                '    cwd = "api"\n',
                file=sys.stderr,
            )
            sys.exit(1)

        # ── Discovery report ───────────────────────────────────────────────────
        _FW_WIDTH = 10
        _DIR_WIDTH = 14
        print(f"  {'SERVICE':<8}  {'FRAMEWORK':<{_FW_WIDTH}}  {'DIR':<{_DIR_WIDTH}}  COMMAND")
        print(f"  {'─'*8}  {'─'*_FW_WIDTH}  {'─'*_DIR_WIDTH}  {'─'*38}")
        for svc in services:
            # Infer framework label from cmd for display
            fw = "unknown"
            cmd_lower = svc.cmd.lower()
            if "uvicorn" in cmd_lower:    fw = "fastapi"
            elif "manage.py" in cmd_lower: fw = "django"
            elif "flask" in cmd_lower:     fw = "flask"
            elif "cargo" in cmd_lower:     fw = "rust"
            elif "go run" in cmd_lower:    fw = "go"
            elif "vite" in cmd_lower or "npm" in cmd_lower or "bun" in cmd_lower or "pnpm" in cmd_lower:
                fw = "node/vite"
            cwd_display = svc.cwd if svc.cwd != "." else "(root)"
            print(
                f"  [{svc.name.upper()}]    {fw:<{_FW_WIDTH}}  "
                f"{cwd_display:<{_DIR_WIDTH}}  {svc.cmd}"
            )
        print()
        print(f"  A {BOLD}dev.toml{RESET} will be saved so you won't be asked again.")
        print()

        # ── Confirmation prompt ────────────────────────────────────────────────
        try:
            answer = input("  Start these services? [Y/n] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)

        if answer in ("n", "no"):
            print("\nRun 'devlauncher init' to configure services manually.")
            sys.exit(0)

        # ── Write dev.toml ─────────────────────────────────────────────────────
        toml_content = services_to_toml(services)
        try:
            Path("dev.toml").write_text(toml_content, encoding="utf-8")
            print(f"\n  {BOLD}dev.toml{RESET} saved. Edit it anytime to adjust services.\n")
        except OSError as e:
            print(f"{YELLOW}⚠  Could not write dev.toml: {e} — continuing without saving.{RESET}")

    # Run install phase before resolving ports or starting services
    _run_install_phase(services)

    services = _resolve_services(services)

    # Print startup header
    print(f"\n{BOLD}devlauncher{RESET}")
    for i, svc in enumerate(services):
        color = _PALETTE[i % len(_PALETTE)]
        print(f"  {color}{BOLD}[{svc.name.upper()}]{RESET} http://localhost:{svc.port}")
    print()

    run_services(services)


if __name__ == "__main__":
    main()
