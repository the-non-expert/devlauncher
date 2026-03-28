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


def _wait_for_ports_free(services: List[Service], timeout: float = 5.0) -> None:
    """Poll until all service ports are free or timeout expires.

    Called after _kill_all to avoid false port-conflict warnings caused by
    the OS not yet releasing ports from the just-killed processes.
    Exits as soon as all ports are free — typically 1-3 polls (100-300ms).
    """
    import socket
    import time
    ports = [svc.port for svc in services]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        busy = []
        for port in ports:
            for host in ("127.0.0.1", "::1"):  # match find_free_port dual-stack check
                try:
                    family = socket.AF_INET if host == "127.0.0.1" else socket.AF_INET6
                    with socket.socket(family, socket.SOCK_STREAM) as s:
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        if s.connect_ex((host, port)) == 0:
                            busy.append(port)
                            break
                except OSError:
                    pass  # IPv6 may not be available on all systems
        if not busy:
            return
        time.sleep(0.1)


def _restart_loop(services: List[Service], original_services: List[Service]) -> None:
    """Run services in a loop, handling soft/hard restart and quit.

    Args:
        services:          Already-resolved services (correct ports, refs expanded).
        original_services: Pre-resolution services — used to re-resolve on hard restart.
    """
    while True:
        action = run_services(services)

        if action == "quit":
            sys.exit(0)

        elif action == "soft_restart":
            print(f"\n{BOLD}Restarting...{RESET}\n", flush=True)
            _wait_for_ports_free(services)
            # services unchanged — same ports, no reinstall

        elif action == "hard_restart":
            print(f"\n{BOLD}Hard restarting...{RESET}\n", flush=True)
            _wait_for_ports_free(original_services)
            _run_install_phase(original_services)
            services = _resolve_services(original_services)


def _print_discovery_report(services: List[Service]) -> None:
    """Print the auto-discovery results table to stdout."""
    _FW_WIDTH = 10
    _DIR_WIDTH = 14
    print(f"  {'SERVICE':<8}  {'FRAMEWORK':<{_FW_WIDTH}}  {'DIR':<{_DIR_WIDTH}}  COMMAND")
    print(f"  {'─'*8}  {'─'*_FW_WIDTH}  {'─'*_DIR_WIDTH}  {'─'*38}")
    for svc in services:
        fw = "unknown"
        cmd_lower = svc.cmd.lower()
        if "uvicorn" in cmd_lower:
            fw = "fastapi"
        elif "manage.py" in cmd_lower:
            fw = "django"
        elif "flask" in cmd_lower:
            fw = "flask"
        elif "cargo" in cmd_lower:
            fw = "rust"
        elif "go run" in cmd_lower:
            fw = "go"
        elif any(x in cmd_lower for x in ("vite", "npm", "bun", "pnpm")):
            fw = "node/vite"
        cwd_display = svc.cwd if svc.cwd != "." else "(root)"
        print(
            f"  [{svc.name.upper()}]    {fw:<{_FW_WIDTH}}  "
            f"{cwd_display:<{_DIR_WIDTH}}  {svc.cmd}"
        )
    print()


def _run_init() -> None:
    """Run auto-discovery and write dev.toml without starting services.

    Intended for first-time setup when the user wants to review the generated
    config before running devlauncher. Does not start any services.
    """
    print(f"{YELLOW}Running auto-discovery...{RESET}\n")
    services, warnings = discover_services()

    for w in warnings:
        print(f"{YELLOW}⚠  {w}{RESET}")

    if not services:
        print(
            "\nNo services detected. Create a dev.toml manually.\n"
            "  Example:\n"
            "    [services.api]\n"
            '    cmd = "uvicorn main:app --reload --port {self.port}"\n'
            "    port = 8000\n"
            '    cwd = "api"\n',
            file=sys.stderr,
        )
        sys.exit(1)

    _print_discovery_report(services)

    config_path = Path("dev.toml")

    if config_path.exists():
        print(f"  {YELLOW}dev.toml already exists.{RESET}")
        try:
            answer = input("  Overwrite? [y/N] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)
        if answer not in ("y", "yes"):
            print("Aborted.")
            sys.exit(0)
    else:
        try:
            answer = input("  Write dev.toml with these services? [Y/n] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)
        if answer in ("n", "no"):
            print("Aborted.")
            sys.exit(0)

    toml_content = services_to_toml(services)
    try:
        config_path.write_text(toml_content, encoding="utf-8")
        print(
            f"\n  {BOLD}dev.toml{RESET} written. "
            f"Edit it, then run {BOLD}devlauncher{RESET} to start services.\n"
        )
    except OSError as e:
        print(f"Error: could not write dev.toml: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        from . import __version__
        print(f"devlauncher {__version__}")
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == "mcp":
        from .mcp_server import run
        run()
        return

    from .mcp_server import ensure_registered
    ensure_registered()

    if len(sys.argv) > 1 and sys.argv[1] == "init":
        _run_init()
        return

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

        # Migrate outdated dev.toml schemas automatically
        from .migration import CURRENT_SCHEMA_VERSION, check_and_migrate, read_schema_version
        if read_schema_version(Path(config_path)) < CURRENT_SCHEMA_VERSION:
            services, changelog = check_and_migrate(Path(config_path), services)
            if changelog:
                print(f"{YELLOW}↑  dev.toml updated to schema v{CURRENT_SCHEMA_VERSION}:{RESET}")
                for line in changelog:
                    print(f"{YELLOW}{line}{RESET}")
                print()

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
        _print_discovery_report(services)
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

    _restart_loop(services, services)


if __name__ == "__main__":
    main()
