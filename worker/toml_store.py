from __future__ import annotations

import errno
import os
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.items import AoT, Table

from app.utils.logging_config import logger

from .config_loader import (
    _coerce_size_bytes,
    _normalize_cron,
    is_valid_project_id,
)
from .constants import APP_DIR, PROJECTS_DIR

_DEFAULT_CONFIG = APP_DIR / "project.toml"

def config_path(file_path: str | Path | None = None) -> Path:
    return Path(file_path) if file_path is not None else _DEFAULT_CONFIG

def list_project_dirs() -> list[str]:
    """扫描 projects/ 下合法子目录名（不含隐藏目录）。"""
    if not PROJECTS_DIR.is_dir():
        return []
    names: list[str] = []
    for child in sorted(PROJECTS_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        if not is_valid_project_id(child.name):
            logger.debug(f"Skipping invalid project dir name: {child.name}")
            continue
        names.append(child.name)
    return names

def _load_document(path: Path) -> tomlkit.TOMLDocument:
    if not path.exists():
        return tomlkit.document()
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return tomlkit.document()
    return tomlkit.parse(text)

def _write_text(path: Path, content: str) -> None:
    """写入并 fsync，尽量保证内容落盘。"""
    with path.open("w", encoding="utf-8") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())

def _atomic_write(path: Path, content: str) -> None:
    """尽量原子写入；Docker 单文件 bind mount 上 replace 会 EBUSY，则回退原地写。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    _write_text(tmp, content)
    try:
        os.replace(tmp, path)
    except OSError as exc:
        if getattr(exc, "errno", None) != errno.EBUSY:
            tmp.unlink(missing_ok=True)
            raise
        # 单文件挂载点不能替换 inode，改为覆盖目标文件内容
        try:
            _write_text(path, content)
        finally:
            tmp.unlink(missing_ok=True)

def read_raw_projects(file_path: str | Path | None = None) -> list[dict[str, Any]]:
    """读取 toml 中已登记的 [[project]]（不做目录存在性过滤）。"""
    path = config_path(file_path)
    try:
        doc = _load_document(path)
    except Exception as exc:
        logger.error(f"read_raw_projects: parse failed: {exc}")
        return []

    raw = doc.get("project")
    if raw is None:
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, (Table, dict)):
            continue
        pid = str(item.get("id", "")).strip()
        if not pid:
            continue
        env_raw = item.get("env") or {}
        env: dict[str, str] = {}
        if isinstance(env_raw, (Table, dict)):
            env = {str(k): str(v) for k, v in env_raw.items()}
        cron_raw = item.get("cron") or {}
        cron: dict[str, Any] = {}
        if isinstance(cron_raw, (Table, dict)):
            cron = {str(k): cron_raw[k] for k in cron_raw}
        logs_size = item.get("logs_size")
        out.append(
            {
                "id": pid,
                "run_command": str(item.get("run_command", "")).strip(),
                "env": env,
                "cron": cron,
                "logs_size": "" if logs_size is None else str(logs_size),
            }
        )
    return out

def _build_project_table(entry: dict[str, Any]) -> Table:
    table = tomlkit.table()
    table["id"] = str(entry["id"]).strip()
    table["run_command"] = str(entry["run_command"]).strip()
    logs_size = entry.get("logs_size")
    if logs_size not in (None, ""):
        table["logs_size"] = str(logs_size)

    env = entry.get("env") or {}
    if isinstance(env, dict) and env:
        env_table = tomlkit.table()
        for key, value in env.items():
            env_table[str(key)] = str(value)
        table["env"] = env_table

    cron = entry.get("cron") or {}
    if isinstance(cron, dict) and cron:
        cron_table = tomlkit.table()
        for key, value in cron.items():
            if value is None or value == "":
                continue
            if isinstance(value, bool):
                cron_table[str(key)] = "true" if value else "false"
            else:
                cron_table[str(key)] = str(value)
        if cron_table:
            table["cron"] = cron_table
    return table

def validate_entry(entry: dict[str, Any], *, require_dir: bool = True) -> str | None:
    """返回错误信息；通过则返回 None。"""
    pid = str(entry.get("id", "")).strip()
    if not is_valid_project_id(pid):
        return f"无效的项目 id：{pid!r}"
    run_command = str(entry.get("run_command", "")).strip()
    if not run_command:
        return "run_command 不能为空"
    if "\n" in run_command or "\r" in run_command:
        return "run_command 必须是单行"
    if require_dir and not (PROJECTS_DIR / pid).is_dir():
        return f"项目目录不存在：{PROJECTS_DIR / pid}"
    env = entry.get("env")
    if env is not None and not isinstance(env, dict):
        return "env 必须是对象"
    cron = entry.get("cron")
    if cron is not None and not isinstance(cron, dict):
        return "cron 必须是对象"
    return None

def upsert_project(entry: dict[str, Any], file_path: str | Path | None = None) -> None:
    err = validate_entry(entry, require_dir=True)
    if err:
        raise ValueError(err)

    path = config_path(file_path)
    doc = _load_document(path)
    pid = str(entry["id"]).strip()
    new_table = _build_project_table(entry)

    existing = doc.get("project")
    new_aot: AoT = tomlkit.aot()
    replaced = False
    if isinstance(existing, AoT) or isinstance(existing, list):
        for item in existing:
            item_id = str(item.get("id", "")).strip() if isinstance(item, (Table, dict)) else ""
            if item_id == pid:
                new_aot.append(new_table)
                replaced = True
            elif isinstance(item, (Table, dict)):
                new_aot.append(item)
    if not replaced:
        new_aot.append(new_table)

    doc["project"] = new_aot
    _atomic_write(path, tomlkit.dumps(doc))
    logger.info(f"upsert_project: wrote {pid} into {path}")

def remove_project(project_id: str, file_path: str | Path | None = None) -> bool:
    pid = str(project_id).strip()
    if not is_valid_project_id(pid):
        raise ValueError(f"无效的项目 id：{pid!r}")

    path = config_path(file_path)
    doc = _load_document(path)
    existing = doc.get("project")
    if existing is None:
        return False

    new_aot: AoT = tomlkit.aot()
    removed = False
    for item in existing:
        item_id = str(item.get("id", "")).strip() if isinstance(item, (Table, dict)) else ""
        if item_id == pid:
            removed = True
            continue
        if isinstance(item, (Table, dict)):
            new_aot.append(item)

    if not removed:
        return False

    if len(new_aot) == 0:
        if "project" in doc:
            del doc["project"]
    else:
        doc["project"] = new_aot

    _atomic_write(path, tomlkit.dumps(doc))
    logger.info(f"remove_project: removed {pid} from {path}")
    return True

def entry_to_cluster(entry: dict[str, Any]) -> dict[str, Any]:
    raw_id = str(entry["id"]).strip()
    return {
        "id": raw_id,
        "project_number": raw_id,
        "name": raw_id,
        "_raw_id": raw_id,
        "run_command": str(entry.get("run_command", "")).strip(),
        "env": {str(k): str(v) for k, v in (entry.get("env") or {}).items()},
        "cron": _normalize_cron(entry.get("cron")),
        "logs_size": _coerce_size_bytes(entry.get("logs_size")),
    }
