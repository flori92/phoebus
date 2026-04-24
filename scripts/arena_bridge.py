#!/usr/bin/env python3
"""Manage the local LMArenaBridge instance used by PHOEBUS.

The bridge repository and its config live under external/ so auth cookies,
browser profiles and third-party code are never committed to this project.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = "https://github.com/CloudWaddie/LMArenaBridge.git"
DEFAULT_ARENA_URL = "http://localhost:8000/api/v1"
FALSE_VALUES = {"0", "false", "no", "off", "disabled", "never"}
TRUE_VALUES = {"1", "true", "yes", "on", "enabled", "always"}


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE entries without printing secrets."""
    if not path.exists():
        return
    raw_env = path.read_text(encoding="utf-8", errors="ignore").replace("\\n", "\n")
    for raw_line in raw_env.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    return default


def bridge_dir() -> Path:
    raw = os.getenv("PHOEBUS_ARENA_BRIDGE_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return ROOT / "external" / "LMArenaBridge"


def arena_url() -> str:
    return (os.getenv("ARENA_URL") or DEFAULT_ARENA_URL).strip() or DEFAULT_ARENA_URL


def arena_root_url() -> str:
    parsed = urlparse(arena_url())
    if not parsed.scheme or not parsed.netloc:
        return "http://localhost:8000"
    path = parsed.path.rstrip("/")
    if path.endswith("/api/v1"):
        path = path[: -len("/api/v1")]
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def local_port_from_arena_url() -> int:
    parsed = urlparse(arena_url())
    if parsed.port:
        return parsed.port
    return 443 if parsed.scheme == "https" else 80


def is_port_open(host: str = "127.0.0.1", port: int = 8000, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def health_url() -> str:
    return f"{arena_root_url().rstrip('/')}/api/v1/health"


def bridge_is_running(timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(health_url(), timeout=timeout) as response:
            return 200 <= response.status < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def normalize_cookie_value(value: str | None) -> str:
    token = (value or "").strip().strip('"').strip("'")
    if not token:
        return ""
    if "arena-auth-prod-v1=" in token:
        token = token.split("arena-auth-prod-v1=", 1)[1].strip()
    if ";" in token:
        token = token.split(";", 1)[0].strip()
    return token.strip()


def env_auth_token() -> str:
    for name in (
        "ARENA_AUTH_PROD_V1",
        "ARENA_AUTH_TOKEN",
        "LMARENA_AUTH_TOKEN",
        "ARENA_COOKIE_HEADER",
    ):
        token = normalize_cookie_value(os.getenv(name))
        if token:
            return token
    return ""


def env_cf_clearance() -> str:
    for name in ("ARENA_CF_CLEARANCE", "CF_CLEARANCE"):
        token = normalize_cookie_value(os.getenv(name))
        if token:
            return token
    return ""


def load_bridge_config(config_file: Path) -> dict:
    try:
        return json.loads(config_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_bridge_config() -> bool:
    """Create/update LMArenaBridge config.json from environment secrets."""
    directory = bridge_dir()
    config_file = directory / "config.json"
    config = load_bridge_config(config_file)

    token = env_auth_token()
    cf_clearance = env_cf_clearance()

    config.setdefault("password", os.getenv("ARENA_BRIDGE_ADMIN_PASSWORD", "admin"))
    config.setdefault("auth_token", "")
    config.setdefault("auth_tokens", [])
    config.setdefault("cf_clearance", "")
    config.setdefault("api_keys", [])
    config.setdefault("usage_stats", {})
    config.setdefault("prune_invalid_tokens", False)
    config.setdefault("persist_arena_auth_cookie", True)

    if token:
        existing = [str(item).strip() for item in config.get("auth_tokens", []) if str(item).strip()]
        config["auth_tokens"] = [token] + [item for item in existing if item != token]
        config["auth_token"] = token

    if cf_clearance:
        config["cf_clearance"] = cf_clearance

    api_key = (os.getenv("ARENA_API_KEY") or os.getenv("ARENA_BRIDGE_API_KEY") or "arena").strip()
    rpm_raw = os.getenv("ARENA_BRIDGE_RATE_LIMIT_RPM", "240")
    try:
        rpm = max(1, int(rpm_raw))
    except ValueError:
        rpm = 240

    api_keys = [item for item in config.get("api_keys", []) if isinstance(item, dict)]
    if api_key and not any(item.get("key") == api_key for item in api_keys):
        api_keys.insert(
            0,
            {
                "name": "PHOEBUS",
                "key": api_key,
                "rpm": rpm,
                "created": int(time.time()),
            },
        )
    config["api_keys"] = api_keys

    directory.mkdir(parents=True, exist_ok=True)
    tmp_file = config_file.with_suffix(".json.tmp")
    tmp_file.write_text(json.dumps(config, indent=2), encoding="utf-8")
    tmp_file.replace(config_file)
    try:
        config_file.chmod(0o600)
    except OSError:
        pass

    has_token = bool(config.get("auth_token") or config.get("auth_tokens"))
    return has_token


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    print(f"[ARENA] $ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=str(cwd or ROOT), check=check)


def ensure_repo(update: bool = False) -> None:
    directory = bridge_dir()
    repo = os.getenv("PHOEBUS_ARENA_BRIDGE_REPO", DEFAULT_REPO)
    if not directory.exists():
        directory.parent.mkdir(parents=True, exist_ok=True)
        git = shutil.which("git")
        if not git:
            raise RuntimeError("git est requis pour cloner LMArenaBridge")
        run([git, "clone", "--depth", "1", repo, str(directory)])
        return

    if update and (directory / ".git").exists():
        git = shutil.which("git")
        if git:
            run([git, "pull", "--ff-only"], cwd=directory, check=False)


def install_requirements(fetch_browser: bool = False) -> None:
    req = bridge_dir() / "requirements.txt"
    if not req.exists():
        raise RuntimeError("requirements.txt introuvable dans LMArenaBridge")
    run([sys.executable, "-m", "pip", "install", "-r", str(req)])
    if fetch_browser:
        run([sys.executable, "-m", "camoufox", "fetch"], check=False)


def setup(args: argparse.Namespace) -> int:
    ensure_repo(update=args.update)
    has_token = write_bridge_config()
    if args.install:
        install_requirements(fetch_browser=args.fetch_browser)
    if has_token:
        print("[ARENA] Config bridge prete (token masque).")
    else:
        print("[ARENA] Config creee, mais aucun token arena-auth-prod-v1 n'est configure.")
    return 0


def start(args: argparse.Namespace) -> int:
    ensure_repo(update=env_bool("PHOEBUS_ARENA_BRIDGE_AUTO_UPDATE", False) or args.update)
    has_token = write_bridge_config()
    allow_anonymous = env_bool("PHOEBUS_ARENA_BRIDGE_ALLOW_ANONYMOUS", True)
    if not has_token and not allow_anonymous:
        print("[ARENA] Token absent: renseignez ARENA_AUTH_PROD_V1 dans .env.")
        return 2
    if not has_token:
        print("[ARENA] Aucun token configure; demarrage en mode anonyme best-effort.")

    if env_bool("PHOEBUS_ARENA_BRIDGE_AUTO_INSTALL", False) or args.install:
        install_requirements(fetch_browser=env_bool("PHOEBUS_ARENA_BRIDGE_FETCH_BROWSER", False))

    port = local_port_from_arena_url()
    if bridge_is_running():
        print(f"[ARENA] Bridge deja disponible sur {arena_root_url()}.")
        return 0
    if is_port_open(port=port):
        print(f"[ARENA] Port {port} deja occupe, mais /api/v1/health ne repond pas.")
        return 1

    print(f"[ARENA] Demarrage LMArenaBridge sur {arena_root_url()} (token masque).")
    os.chdir(bridge_dir())
    os.execv(sys.executable, [sys.executable, "-m", "src.main"])
    return 0


def status(_: argparse.Namespace) -> int:
    directory = bridge_dir()
    config = load_bridge_config(directory / "config.json")
    has_repo = (directory / "src" / "main.py").exists()
    has_token = bool(config.get("auth_token") or config.get("auth_tokens") or env_auth_token())
    running = bridge_is_running()
    print(f"repo={has_repo}")
    print(f"config={bool(config)}")
    print(f"token={has_token}")
    print(f"anonymous_allowed={env_bool('PHOEBUS_ARENA_BRIDGE_ALLOW_ANONYMOUS', True)}")
    print(f"running={running}")
    print(f"url={arena_url()}")
    return 0 if has_repo and (has_token or env_bool("PHOEBUS_ARENA_BRIDGE_ALLOW_ANONYMOUS", True)) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gestion du bridge Arena pour PHOEBUS.")
    sub = parser.add_subparsers(dest="command", required=True)

    setup_cmd = sub.add_parser("setup", help="clone et prepare LMArenaBridge")
    setup_cmd.add_argument("--update", action="store_true", help="met a jour le clone existant")
    setup_cmd.add_argument("--install", action="store_true", help="installe les dependances Python du bridge")
    setup_cmd.add_argument("--fetch-browser", action="store_true", help="telecharge le navigateur Camoufox")
    setup_cmd.set_defaults(func=setup)

    start_cmd = sub.add_parser("start", help="prepare puis lance le bridge")
    start_cmd.add_argument("--update", action="store_true", help="met a jour le clone existant")
    start_cmd.add_argument("--install", action="store_true", help="installe les dependances avant lancement")
    start_cmd.set_defaults(func=start)

    status_cmd = sub.add_parser("status", help="affiche l'etat sans reveler les secrets")
    status_cmd.set_defaults(func=status)
    return parser


def main(argv: list[str] | None = None) -> int:
    load_env_file(ROOT / ".env")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1
    except Exception as exc:
        print(f"[ARENA] Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
