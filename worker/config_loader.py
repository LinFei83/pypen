from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from app.utils.logging_config import logger

from .constants import PROJECTS_DIR

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

_REQUIRED_KEYS = ("id", "run_command")

_CRON_DEFAULTS: dict[str, Any] = {
    "restart_on": None,
    "redeploy": False,
    "idle": None,
    "pull_commits": False,
}

_DEFAULT_LOGS_SIZE_BYTES: int = 10 * 1024 * 1024

_SIZE_SUFFIXES: dict[str, int] = {
    "": 1,
    "B": 1,
    "K": 1024,
    "KB": 1024,
    "M": 1024 * 1024,
    "MB": 1024 * 1024,
    "G": 1024 * 1024 * 1024,
    "GB": 1024 * 1024 * 1024,
}

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on")
    return bool(value)

def _coerce_optional_int(value: Any) -> int | None:
    if value in (None, "", 0, "0"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def _coerce_size_bytes(value: Any) -> int:
    if value in (None, "", 0, "0"):
        return _DEFAULT_LOGS_SIZE_BYTES
    if isinstance(value, (int, float)):
        return max(int(value), 4096)
    text = str(value).strip().upper().replace(" ", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([A-Z]*)", text)
    if not match:
        return _DEFAULT_LOGS_SIZE_BYTES
    number, suffix = match.groups()
    multiplier = _SIZE_SUFFIXES.get(suffix)
    if multiplier is None:
        return _DEFAULT_LOGS_SIZE_BYTES
    return max(int(float(number) * multiplier), 4096)

def _normalize_dnf_packages(raw: Any) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        items = raw.split()
    elif isinstance(raw, (list, tuple)):
        items = [str(x) for x in raw]
    else:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        name = item.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out

def load_defaults(file_path: str) -> dict[str, Any]:
    path = Path(file_path)
    if not path.exists():
        return {"dnf_packages": [], "ping": True, "ping_url": ""}
    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        logger.error(f"load_defaults: TOML parse error in {file_path}: {exc}")
        return {"dnf_packages": [], "ping": True, "ping_url": ""}
    defaults = raw.get("defaults") or {}
    if not isinstance(defaults, dict):
        return {"dnf_packages": [], "ping": True, "ping_url": ""}
    ping_raw = defaults.get("ping", True)
    return {
        "dnf_packages": _normalize_dnf_packages(defaults.get("dnf_packages")),
        "ping": _coerce_bool(ping_raw) if ping_raw not in (None, "") else True,
        "ping_url": str(defaults.get("ping_url") or "").strip(),
    }

def _normalize_cron(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    return {
        "restart_on": _coerce_optional_int(raw.get("restart_on")),
        "redeploy": _coerce_bool(raw.get("redeploy", False)),
        "idle": _coerce_optional_int(raw.get("idle")),
        "pull_commits": _coerce_bool(raw.get("pull_commits", False)),
    }

_TOKEN_URL_RE = re.compile(r"^(https?://)(?:[^@/]+@)?(.+)$", re.IGNORECASE)

def inject_access_token(git_url: str, token: str | None) -> str:
    """保留供本地 git remote 鉴权等场景复用；主启动路径不再使用。"""
    if not token:
        return git_url
    url = (git_url or "").strip()
    match = _TOKEN_URL_RE.match(url)
    if not match:
        return url
    scheme, rest = match.groups()
    return f"{scheme}x-access-token:{token}@{rest}"

def _is_valid_project_id(project_id: str) -> bool:
    if not project_id or project_id.startswith("."):
        return False
    if "/" in project_id or "\\" in project_id:
        return False
    return bool(_ID_RE.fullmatch(project_id))

def validate_config(projects: list[dict[str, Any]]) -> bool:
    seen_ids: set[str] = set()

    for project in projects:
        missing = [k for k in _REQUIRED_KEYS if not project.get(k)]
        if missing:
            logger.error(
                f"Missing required fields {missing} in project: "
                f"{project.get('_raw_id', '<unnamed>')}"
            )
            return False

        raw_id = project["_raw_id"]
        if not _is_valid_project_id(raw_id):
            logger.error(
                f"Invalid project id {raw_id!r}: must match "
                f"{_ID_RE.pattern} and not contain path separators"
            )
            return False

        project_dir = PROJECTS_DIR / raw_id
        if not project_dir.is_dir():
            logger.error(
                f"Project directory missing for id={raw_id}: expected {project_dir}"
            )
            return False

        if raw_id in seen_ids:
            logger.error(f"Duplicate project id: {raw_id}")
            return False
        seen_ids.add(raw_id)

    logger.info("Configuration validation successful.")
    return True

def load_config(file_path: str) -> list[dict[str, Any]]:
    logger.info(f"Loading configuration from {file_path}")

    path = Path(file_path)
    if not path.exists():
        logger.error(f"Configuration file not found: {file_path}")
        return []

    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as e:
        logger.error(f"Error parsing TOML file: {e}")
        return []

    projects_raw = raw.get("project", []) or []
    if not isinstance(projects_raw, list):
        logger.error("[[project]] must be an array of tables.")
        return []

    projects: list[dict[str, Any]] = []
    for entry in projects_raw:
        raw_id = str(entry.get("id", "")).strip()
        if not raw_id:
            logger.warning("Skipping project with empty id.")
            continue

        if not _is_valid_project_id(raw_id):
            logger.error(
                f"Skipping project with invalid id {raw_id!r} "
                f"(must be a safe folder name under {PROJECTS_DIR})"
            )
            continue

        run_command = str(entry.get("run_command", "")).strip()
        if not run_command:
            logger.error(f"Skipping project {raw_id}: run_command is required")
            continue
        if "\n" in run_command or "\r" in run_command:
            logger.error(f"Skipping project {raw_id}: run_command must be a single line")
            continue

        project_dir = PROJECTS_DIR / raw_id
        if not project_dir.is_dir():
            logger.error(
                f"Skipping project {raw_id}: directory not found at {project_dir}"
            )
            continue

        env = entry.get("env") or {}
        if not isinstance(env, dict):
            logger.warning(f"Ignoring non-table [project.env] for {raw_id}.")
            env = {}

        projects.append(
            {
                "id": raw_id,
                "project_number": raw_id,
                "name": raw_id,
                "_raw_id": raw_id,
                "run_command": run_command,
                "env": {str(k): str(v) for k, v in env.items()},
                "cron": _normalize_cron(entry.get("cron")),
                "logs_size": _coerce_size_bytes(entry.get("logs_size")),
            }
        )

    if projects and not validate_config(projects):
        raise ValueError("Invalid configuration file.")

    return projects
