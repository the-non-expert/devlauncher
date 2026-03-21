"""dev.toml config loading and port-reference resolution.

Config format:

    [services.api]
    cmd = "uvicorn main:app --reload"
    port = 8000
    cwd = "api"

    [services.web]
    cmd = "npm run dev"
    port = 5173
    cwd = "frontend"
    env = { PUBLIC_API_URL = "http://localhost:{api.port}" }

Port references like {api.port} are resolved after conflict detection,
so if the API lands on 8001 instead of 8000, PUBLIC_API_URL gets the
correct URL automatically.
"""

import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, List

# tomllib is stdlib in Python 3.11+; fall back to tomli on 3.9-3.10
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError as exc:
        raise ImportError(
            "Python < 3.11 requires the 'tomli' package: pip install tomli"
        ) from exc


@dataclass(frozen=True)
class Service:
    name: str
    cmd: str
    port: int
    cwd: str = "."
    env: Dict[str, str] = field(default_factory=dict)


def load_config(path: str = "dev.toml") -> List[Service]:
    """Parse dev.toml and return services in declaration order."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with config_path.open("rb") as f:
        data = tomllib.load(f)

    services = []
    for name, cfg in data.get("services", {}).items():
        if "cmd" not in cfg:
            raise ValueError(f"Service '{name}' is missing required field 'cmd'")
        if "port" not in cfg:
            raise ValueError(f"Service '{name}' is missing required field 'port'")
        services.append(Service(
            name=name,
            cmd=cfg["cmd"],
            port=int(cfg["port"]),
            cwd=cfg.get("cwd", "."),
            env={k: str(v) for k, v in cfg.get("env", {}).items()},
        ))

    if not services:
        raise ValueError("No services defined in dev.toml")

    return services


_REF_PATTERN = re.compile(r"\{(\w+)\.port\}")


def resolve_port_refs(
    services: List[Service],
    resolved_ports: Dict[str, int],
) -> List[Service]:
    """Replace {name.port} placeholders with actual resolved ports.

    Called after find_free_port() has run for each service, so references
    always reflect the real port in use (not the preferred default).
    """
    def _replace(m: re.Match) -> str:
        ref = m.group(1)
        if ref in resolved_ports:
            return str(resolved_ports[ref])
        return m.group(0)  # leave unresolved refs as-is

    result = []
    for svc in services:
        # Build a resolver that also handles {self.port} as an alias
        # for the current service's own resolved port.
        self_ports = {**resolved_ports, "self": resolved_ports.get(svc.name, svc.port)}

        def _replace_with_self(m: re.Match, _sp: dict = self_ports) -> str:
            ref = m.group(1)
            if ref in _sp:
                return str(_sp[ref])
            return m.group(0)

        resolved_cmd = _REF_PATTERN.sub(_replace_with_self, svc.cmd)
        resolved_env = {
            key: _REF_PATTERN.sub(_replace_with_self, val)
            for key, val in svc.env.items()
        }
        result.append(replace(svc, cmd=resolved_cmd, env=resolved_env))
    return result
