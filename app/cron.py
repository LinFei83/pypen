from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from app import app
from app.utils.logging_config import logger

CONFIG_FILE = Path("/app/project.toml")

IDLE_CHECK_INTERVAL_SEC = 60

_TASKS: list[asyncio.Task] = []

def _truthy(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in {"true", "yes", "1", "on"}

def _coerce_positive_int(val: Any) -> int | None:
    if val in (None, "", 0, "0"):
        return None
    try:
        n = int(val)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None

def _load_project_crons() -> list[tuple[str, dict[str, Any]]]:
    try:
        with CONFIG_FILE.open("rb") as fh:
            raw = tomllib.load(fh)
    except (FileNotFoundError, tomllib.TOMLDecodeError) as exc:
        logger.warning(f"cron: cannot read {CONFIG_FILE}: {exc}")
        return []

    out: list[tuple[str, dict[str, Any]]] = []
    for entry in raw.get("project") or []:
        if not isinstance(entry, dict):
            continue
        raw_id = str(entry.get("id", "")).strip()
        if not raw_id:
            continue
        cron = entry.get("cron") or {}
        if not isinstance(cron, dict):
            continue
        out.append((raw_id, cron))
    return out

def _resolve_service_name(raw_id: str) -> str | None:
    from app.routes.routes import list_services

    for svc in list_services():
        if svc == raw_id:
            return svc
    return None

async def _do_start(service: str) -> None:
    from app.routes.routes import (
        _restore_run,
        _svc_path,
        _wait_for_status,
        broadcast_status_update,
        s6_rescan,
        s6_svc,
        update_process_code,
    )

    if not _restore_run(service) and not (_svc_path(service) / "run").exists():
        logger.warning(f"cron: cannot start {service}: no run script")
        return
    update_process_code(service)
    s6_rescan()
    result = s6_svc("-u", service)
    if result["status"] != "success":
        logger.error(f"cron: start {service} failed: {result['message']}")
        return
    await _wait_for_status(service, "RUNNING")
    await broadcast_status_update()

async def _do_restart(service: str) -> None:
    from app.routes.routes import (
        _wait_for_status,
        broadcast_status_update,
        delete_service_logs,
        s6_svc,
        thoroughly_cleanup,
        update_process_code,
    )

    thoroughly_cleanup(service)
    delete_service_logs(service)
    update_process_code(service)
    result = s6_svc("-r", service)
    if result["status"] != "success":
        logger.error(f"cron: restart {service} failed: {result['message']}")
        return
    await _wait_for_status(service, "RUNNING")
    await broadcast_status_update()

async def _do_redeploy(service: str) -> None:
    from app.routes.routes import (
        FAILURE_COUNTS,
        PAUSED_BY_SYSTEM,
        _find_project_config,
        _kill_orphans,
        _redeploy_blocking,
        _run_cmd,
        _svc_path,
        _wait_for_status,
        broadcast_status_update,
        delete_service_logs,
        s6_rescan,
        s6_svc,
    )

    project = _find_project_config(service)
    if project is None:
        logger.warning(f"cron: redeploy skipped for {service}: no project entry")
        return

    _run_cmd(
        ["s6-svc", "-wD", "-d", str(_svc_path(service))],
        timeout=15,
    )
    _kill_orphans(service)
    await _wait_for_status(service, None)

    await asyncio.get_event_loop().run_in_executor(
        None, _redeploy_blocking, service, project
    )

    FAILURE_COUNTS[service] = 0
    PAUSED_BY_SYSTEM.discard(service)
    delete_service_logs(service)
    s6_rescan()
    result = s6_svc("-u", service)
    if result["status"] != "success":
        logger.error(f"cron: redeploy bring-up failed for {service}: {result['message']}")
        return
    await _wait_for_status(service, "RUNNING")
    await broadcast_status_update()

async def _scheduled_restart_loop(
    raw_id: str, hours: int, redeploy_on_restart: bool
) -> None:
    interval = hours * 3600
    logger.info(
        f"cron: scheduled-restart armed for {raw_id} every {hours}h "
        f"(redeploy={redeploy_on_restart})"
    )
    while True:
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return

        service = _resolve_service_name(raw_id)
        if service is None:
            logger.info(
                f"cron: scheduled-restart for {raw_id} skipped (service not ready)"
            )
            continue

        action = "sync-code" if redeploy_on_restart else "restart"
        logger.info(f"cron: scheduled {action} firing for {service}")
        try:
            if redeploy_on_restart:
                await _do_redeploy(service)
            else:
                await _do_restart(service)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.exception(f"cron: scheduled {action} failed for {service}: {exc}")

async def _idle_loop(raw_id: str, minutes: int) -> None:
    threshold = minutes * 60
    logger.info(
        f"cron: idle auto-start armed for {raw_id} after {minutes}m STOPPED"
    )
    stopped_for = 0.0
    while True:
        try:
            await asyncio.sleep(IDLE_CHECK_INTERVAL_SEC)
        except asyncio.CancelledError:
            return

        service = _resolve_service_name(raw_id)
        if service is None:
            stopped_for = 0.0
            continue

        from app.routes.routes import s6_svstat

        parsed = s6_svstat(service)
        if parsed is None:
            stopped_for = 0.0
            continue

        if parsed["status"] == "STOPPED":
            stopped_for += IDLE_CHECK_INTERVAL_SEC
            if stopped_for >= threshold:
                logger.info(
                    f"cron: idle threshold reached for {service}, auto-starting"
                )
                try:
                    await _do_start(service)
                except asyncio.CancelledError:
                    return
                except Exception as exc:
                    logger.exception(
                        f"cron: idle auto-start failed for {service}: {exc}"
                    )
                stopped_for = 0.0
        else:
            stopped_for = 0.0

@app.before_serving
async def _start_cron_tasks() -> None:
    await _launch_cron_tasks()
    logger.info(f"cron: launched {len(_TASKS)} background task(s)")

@app.after_serving
async def _stop_cron_tasks() -> None:
    await _cancel_cron_tasks()

async def _cancel_cron_tasks() -> None:
    for task in _TASKS:
        task.cancel()
    for task in _TASKS:
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    _TASKS.clear()

async def _launch_cron_tasks() -> None:
    for raw_id, cron in _load_project_crons():
        restart_hours = _coerce_positive_int(cron.get("restart_on"))
        if restart_hours:
            redeploy_flag = _truthy(cron.get("redeploy"))
            _TASKS.append(
                asyncio.create_task(
                    _scheduled_restart_loop(raw_id, restart_hours, redeploy_flag),
                    name=f"cron-restart-{raw_id}",
                )
            )

        idle_minutes = _coerce_positive_int(cron.get("idle"))
        if idle_minutes:
            _TASKS.append(
                asyncio.create_task(
                    _idle_loop(raw_id, idle_minutes),
                    name=f"cron-idle-{raw_id}",
                )
            )

async def reload_cron_tasks() -> None:
    """配置变更后热重载定时任务（无需重启容器）。"""
    logger.info("cron: reloading background tasks…")
    await _cancel_cron_tasks()
    await _launch_cron_tasks()
    logger.info(f"cron: reloaded {len(_TASKS)} background task(s)")
