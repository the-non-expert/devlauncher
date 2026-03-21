"""Auto-discovery: infer services from project structure without a dev.toml.

Scans the project directory, collects evidence (signals) per subdirectory,
scores each directory for frontend/backend roles, and returns the best
match per role as a list of Service objects ready for the runner.

Accuracy is intentional: confident detections start silently, uncertain ones
warn the user, and anything too ambiguous recommends `devmux init` instead.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import Service

# ── Signal weights ─────────────────────────────────────────────────────────────
HIGH   = 3
MEDIUM = 2
LOW    = 1

# ── Confidence thresholds ──────────────────────────────────────────────────────
CONFIDENT  = "CONFIDENT"   # score >= 6
LIKELY     = "LIKELY"      # score 4–5
PLAUSIBLE  = "PLAUSIBLE"   # score == 3
UNCERTAIN  = "UNCERTAIN"   # score 1–2
SKIP       = "SKIP"        # score == 0


def _score_to_confidence(score: int) -> str:
    if score >= 6: return CONFIDENT
    if score >= 4: return LIKELY
    if score >= 3: return PLAUSIBLE
    if score >= 1: return UNCERTAIN
    return SKIP


# ── Directories to skip during scan ───────────────────────────────────────────
_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", ".svelte-kit", ".nuxt", "target",
    "coverage", ".coverage", "docs", "tests", "test", "scripts",
    ".github", ".idea", ".vscode", "tmp", "temp", "logs", ".cache",
    "static", "public", "assets", "migrations",
}


# ── Internal result types ──────────────────────────────────────────────────────
@dataclass
class _DirScore:
    path: Path
    frontend_score: int = 0
    backend_score: int = 0
    frontend_framework: Optional[str] = None
    backend_framework: Optional[str] = None
    package_manager: str = "npm"
    warnings: List[str] = field(default_factory=list)


@dataclass
class DiscoveredService:
    name: str
    role: str           # "frontend" | "backend"
    cmd: str
    port: int
    cwd: str
    confidence: str
    framework: str
    warnings: List[str] = field(default_factory=list)


# ── Helpers ────────────────────────────────────────────────────────────────────
def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, json.JSONDecodeError):
        return {}


def _has_dep(text: str, *names: str) -> bool:
    """Case-insensitive check for package names in a deps file."""
    lower = text.lower()
    return any(name.lower() in lower for name in names)


def _detect_package_manager(directory: Path) -> str:
    if (directory / "bun.lockb").exists():
        return "bun"
    if (directory / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (directory / "yarn.lock").exists():
        return "yarn"
    return "npm"


def _npm_dev_cmd(pm: str, port_ref: str) -> str:
    """Build the dev command for a given package manager."""
    if pm == "bun":
        return f"bun run dev -- --port {port_ref}"
    if pm == "pnpm":
        return f"pnpm run dev -- --port {port_ref}"
    if pm == "yarn":
        return f"yarn dev --port {port_ref}"
    return f"npm run dev -- --port {port_ref}"


# ── Directory scorer ───────────────────────────────────────────────────────────
def _score_directory(directory: Path) -> _DirScore:
    result = _DirScore(path=directory)
    name = directory.name.lower()

    # ── Package manager ────────────────────────────────────────────────────────
    result.package_manager = _detect_package_manager(directory)

    # ── package.json analysis ──────────────────────────────────────────────────
    pkg_json = _read_json(directory / "package.json")
    has_pkg = bool(pkg_json)
    scripts = pkg_json.get("scripts", {})
    deps = {
        **pkg_json.get("dependencies", {}),
        **pkg_json.get("devDependencies", {}),
    }
    has_dev_script = "dev" in scripts
    has_start_script = "start" in scripts

    # Detect JS frontend frameworks from package.json deps
    if has_pkg:
        if "vite" in deps or "vite" in pkg_json.get("devDependencies", {}):
            result.frontend_score += HIGH
            result.frontend_framework = "vite"
        if "next" in deps:
            result.frontend_score += HIGH
            result.frontend_framework = "nextjs"
        if "nuxt" in deps:
            result.frontend_score += HIGH
            result.frontend_framework = "nuxt"
        if "@angular/core" in deps:
            result.frontend_score += HIGH
            result.frontend_framework = "angular"
        if "svelte" in deps or "@sveltejs/kit" in deps:
            result.frontend_score += HIGH
            result.frontend_framework = "svelte"

        if has_dev_script:
            result.frontend_score += HIGH
        elif has_start_script:
            result.backend_score += MEDIUM  # node backend pattern
        elif has_pkg:
            result.frontend_score += MEDIUM

    # ── Framework config files ─────────────────────────────────────────────────
    for pattern in ("vite.config.ts", "vite.config.js", "vite.config.mjs"):
        if (directory / pattern).exists():
            result.frontend_score += HIGH
            result.frontend_framework = result.frontend_framework or "vite"
            break

    for pattern in ("next.config.js", "next.config.ts", "next.config.mjs"):
        if (directory / pattern).exists():
            result.frontend_score += HIGH
            result.frontend_framework = result.frontend_framework or "nextjs"
            break

    for pattern in ("nuxt.config.js", "nuxt.config.ts"):
        if (directory / pattern).exists():
            result.frontend_score += HIGH
            result.frontend_framework = result.frontend_framework or "nuxt"
            break

    for pattern in ("svelte.config.js", "svelte.config.ts"):
        if (directory / pattern).exists():
            result.frontend_score += HIGH
            result.frontend_framework = result.frontend_framework or "svelte"
            break

    if (directory / "angular.json").exists():
        result.frontend_score += HIGH
        result.frontend_framework = result.frontend_framework or "angular"

    # ── Python backend signals ─────────────────────────────────────────────────
    python_deps_text = ""
    for deps_file in ("requirements.txt", "requirements-dev.txt"):
        p = directory / deps_file
        if p.exists():
            python_deps_text += _read_text(p)

    pyproject = directory / "pyproject.toml"
    if pyproject.exists():
        python_deps_text += _read_text(pyproject)

    if python_deps_text:
        if _has_dep(python_deps_text, "fastapi", "uvicorn"):
            result.backend_score += HIGH
            result.backend_framework = "fastapi"
        elif _has_dep(python_deps_text, "flask"):
            result.backend_score += HIGH
            result.backend_framework = "flask"
        elif _has_dep(python_deps_text, "django"):
            result.backend_score += HIGH
            result.backend_framework = "django"

    if (directory / "manage.py").exists():
        result.backend_score += HIGH
        result.backend_framework = result.backend_framework or "django"

    if (directory / "main.py").exists():
        result.backend_score += LOW
        result.backend_framework = result.backend_framework or "python"

    if (directory / "app.py").exists():
        result.backend_score += LOW
        result.backend_framework = result.backend_framework or "flask"

    # ── Rust backend ───────────────────────────────────────────────────────────
    cargo = directory / "Cargo.toml"
    if cargo.exists():
        cargo_text = _read_text(cargo)
        if _has_dep(cargo_text, "axum", "actix-web", "rocket", "warp"):
            result.backend_score += HIGH
            result.backend_framework = "rust"
        else:
            result.backend_score += MEDIUM
            result.backend_framework = result.backend_framework or "rust"

    # ── Go backend ─────────────────────────────────────────────────────────────
    if (directory / "go.mod").exists():
        result.backend_score += MEDIUM
        result.backend_framework = result.backend_framework or "go"
    if (directory / "main.go").exists():
        result.backend_score += MEDIUM
        result.backend_framework = result.backend_framework or "go"

    # ── Directory name bonuses ─────────────────────────────────────────────────
    if name in ("frontend", "web", "client", "app", "ui"):
        result.frontend_score += MEDIUM
    if name in ("api", "backend", "server", "service"):
        result.backend_score += MEDIUM

    return result


# ── Command + port inference ───────────────────────────────────────────────────
def _infer_frontend(score: _DirScore) -> Tuple[str, int]:
    """Return (command, default_port) for a frontend service."""
    pm = score.package_manager
    fw = score.frontend_framework or "vite"

    if fw == "nextjs":
        cmd = f"{pm} run dev -- -p {{self.port}}" if pm == "npm" else f"{pm} run dev -- --port {{self.port}}"
        return cmd, 3000
    if fw == "nuxt":
        return _npm_dev_cmd(pm, "{self.port}"), 3000
    if fw == "angular":
        return f"ng serve --port {{self.port}}", 4200
    # vite / svelte / generic
    return _npm_dev_cmd(pm, "{self.port}"), 5173


def _infer_backend(score: _DirScore) -> Tuple[str, int, List[str]]:
    """Return (command, default_port, warnings) for a backend service."""
    fw = score.backend_framework or "python"
    warnings: List[str] = []

    if fw == "fastapi":
        # Try to find the entry point
        directory = score.path
        entry = "main:app"
        for candidate in ("main.py", "app.py", "server.py", "run.py"):
            if (directory / candidate).exists():
                module = candidate.replace(".py", "")
                entry = f"{module}:app"
                break
        if entry == "main:app" and not (directory / "main.py").exists():
            warnings.append(f"Could not find FastAPI entry point — defaulting to 'main:app'. Update dev.toml if wrong.")
        return f"uvicorn {entry} --reload --port {{self.port}}", 8000, warnings

    if fw == "flask":
        return "flask run --port {self.port}", 5000, warnings

    if fw == "django":
        return "python manage.py runserver {self.port}", 8000, warnings

    if fw == "rust":
        warnings.append("Rust detected — command defaults to 'cargo run'. Port injection via PORT env var may be needed.")
        return "cargo run", 8080, warnings

    if fw == "go":
        warnings.append("Go detected — command defaults to 'go run .'. You may need to handle port binding in your code.")
        return "go run .", 8080, warnings

    # Generic node backend
    return "npm run start", 3000, warnings


# ── Install command inference ──────────────────────────────────────────────────
def _infer_install_cmd(score: _DirScore) -> Optional[str]:
    """Return the install command for a discovered service, or None if not applicable.

    Rules:
    - Node project (has package.json): use package-manager-specific install
    - Python project with requirements.txt: "pip install -r requirements.txt"
    - Python project with only pyproject.toml: "pip install -e ."
    - Go project (go.mod present): "go mod download"
    - Rust / anything else: None (cargo fetches deps on build; no pre-install step)
    """
    directory = score.path

    # Node — package.json present
    if (directory / "package.json").exists():
        pm = score.package_manager
        if pm == "bun":
            return "bun install"
        if pm == "pnpm":
            return "pnpm install"
        if pm == "yarn":
            return "yarn install"
        return "npm install"

    # Python — requirements.txt takes priority over pyproject-only
    has_requirements = (
        (directory / "requirements.txt").exists()
        or (directory / "requirements-dev.txt").exists()
    )
    has_pyproject = (directory / "pyproject.toml").exists()
    if has_requirements:
        return "pip install -r requirements.txt"
    if has_pyproject:
        return "pip install -e ."

    # Go
    if (directory / "go.mod").exists():
        return "go mod download"

    return None


# ── Monorepo detection ─────────────────────────────────────────────────────────
def _is_monorepo(root: Path) -> bool:
    """Heuristic: looks like a monorepo if packages/ or apps/ exist with 2+ subdirs."""
    for dirname in ("packages", "apps"):
        candidate = root / dirname
        if candidate.is_dir():
            subdirs = [d for d in candidate.iterdir() if d.is_dir()]
            if len(subdirs) >= 2:
                return True
    return False


# ── Main discovery function ────────────────────────────────────────────────────
def discover_services(root: Optional[str] = None) -> Tuple[List[Service], List[str]]:
    """Scan project and return (services, warnings).

    Returns up to 2 services (one frontend, one backend).
    Warnings are printed by the caller before starting.
    """
    root_path = Path(root) if root else Path.cwd()
    warnings: List[str] = []

    # Monorepo guard
    if _is_monorepo(root_path):
        warnings.append(
            "Monorepo structure detected (packages/ or apps/ with multiple subdirs). "
            "Auto-discovery may be inaccurate. Run 'devmux init' to create a dev.toml."
        )

    # Scan candidate directories (immediate subdirs + root itself)
    candidates: List[_DirScore] = []

    # Check root
    root_score = _score_directory(root_path)
    root_score.path = root_path
    if root_score.frontend_score > 0 or root_score.backend_score > 0:
        candidates.append(root_score)

    # Check subdirs
    for entry in sorted(root_path.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name in _SKIP_DIRS or entry.name.startswith("."):
            continue
        score = _score_directory(entry)
        if score.frontend_score > 0 or score.backend_score > 0:
            candidates.append(score)

    # Pick best frontend and backend
    frontend_candidates = sorted(
        [c for c in candidates if c.frontend_score > 0],
        key=lambda c: c.frontend_score, reverse=True,
    )
    backend_candidates = sorted(
        [c for c in candidates if c.backend_score > 0],
        key=lambda c: c.backend_score, reverse=True,
    )

    # Warn if multiple strong candidates per role
    if len(frontend_candidates) >= 2:
        top, second = frontend_candidates[0], frontend_candidates[1]
        if second.frontend_score >= HIGH:
            warnings.append(
                f"Multiple frontend candidates found: '{top.path.name}' (score {top.frontend_score}) "
                f"and '{second.path.name}' (score {second.frontend_score}). "
                f"Using '{top.path.name}'. Run 'devmux init' if wrong."
            )

    if len(backend_candidates) >= 2:
        top, second = backend_candidates[0], backend_candidates[1]
        if second.backend_score >= HIGH:
            warnings.append(
                f"Multiple backend candidates found: '{top.path.name}' (score {top.backend_score}) "
                f"and '{second.path.name}' (score {second.backend_score}). "
                f"Using '{top.path.name}'. Run 'devmux init' if wrong."
            )

    services: List[Service] = []

    # Build frontend service
    if frontend_candidates:
        fs = frontend_candidates[0]
        confidence = _score_to_confidence(fs.frontend_score)
        if confidence != SKIP:
            cmd, port = _infer_frontend(fs)
            cwd = str(fs.path.relative_to(root_path)) if fs.path != root_path else "."
            svc_warnings = list(fs.warnings)
            if confidence == UNCERTAIN:
                svc_warnings.append(
                    f"Low confidence for frontend in '{fs.path.name}' (score {fs.frontend_score}). "
                    "Run 'devmux init' to verify."
                )
            services.append(Service(
                name="web",
                cmd=cmd,
                port=port,
                cwd=cwd,
                env={},
                install_cmd=_infer_install_cmd(fs),
            ))
            warnings.extend(svc_warnings)
    else:
        warnings.append("No frontend service detected.")

    # Build backend service
    if backend_candidates:
        bs = backend_candidates[0]
        confidence = _score_to_confidence(bs.backend_score)
        if confidence != SKIP:
            cmd, port, extra_warnings = _infer_backend(bs)
            cwd = str(bs.path.relative_to(root_path)) if bs.path != root_path else "."
            svc_warnings = list(bs.warnings) + extra_warnings
            if confidence == UNCERTAIN:
                svc_warnings.append(
                    f"Low confidence for backend in '{bs.path.name}' (score {bs.backend_score}). "
                    "Run 'devmux init' to verify."
                )
            services.append(Service(
                name="api",
                cmd=cmd,
                port=port,
                cwd=cwd,
                env={},
                install_cmd=_infer_install_cmd(bs),
            ))
            warnings.extend(svc_warnings)
    else:
        warnings.append("No backend service detected.")

    # 3+ services total → recommend dev.toml
    total = len(frontend_candidates) + len(backend_candidates)
    if total >= 4:
        warnings.append(
            f"{total} potential services found. "
            "For complex projects, 'devmux init' is strongly recommended."
        )

    return services, warnings


# ── TOML serialisation ─────────────────────────────────────────────────────────
def services_to_toml(services: List[Service]) -> str:
    """Serialise discovered services to a dev.toml string.

    Written when the user confirms auto-discovery results, so subsequent
    runs skip discovery entirely and use this file directly.
    """
    lines: List[str] = [
        "# Generated by devmux auto-discovery.",
        "# Edit freely — devmux will use this file on all future runs.",
        "",
    ]
    for svc in services:
        lines.append(f"[services.{svc.name}]")
        lines.append(f'cmd = "{svc.cmd}"')
        lines.append(f"port = {svc.port}")
        lines.append(f'cwd = "{svc.cwd}"')
        if svc.install_cmd:
            lines.append(f'install_cmd = "{svc.install_cmd}"')
        if svc.env:
            env_parts = ", ".join(
                f'{k} = "{v}"' for k, v in svc.env.items()
            )
            lines.append(f"env = {{ {env_parts} }}")
        lines.append("")
    return "\n".join(lines)
