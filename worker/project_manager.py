from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.utils.logging_config import logger

from .constants import PROJECTS_DIR, S6_SERVICE_DIR
from .s6_config import teardown_service, write_service
from .s6_svc import (
    rescan_services,
)

def _project_dir(cluster: dict[str, Any]) -> Path:
    return PROJECTS_DIR / cluster["project_number"].replace(" ", "_")

def install_system_packages(packages: list[str]) -> None:
    if not packages:
        return

    dnf = shutil.which("dnf") or shutil.which("dnf5")
    if dnf is None:
        logger.warning(
            f"install_system_packages: dnf not found on PATH; skipping {packages}"
        )
        return

    cmd = [
        dnf, "install", "-y",
        "--setopt=install_weak_deps=False",
        *packages,
    ]
    logger.info(f"install_system_packages: running {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600
        )
    except subprocess.TimeoutExpired:
        logger.error("install_system_packages: dnf install timed out after 600s")
        return
    except Exception as exc:
        logger.error(f"install_system_packages: dnf invocation failed: {exc}")
        return

    for line in (result.stdout or "").splitlines():
        logger.info(f"[dnf] {line}")
    for line in (result.stderr or "").splitlines():
        log_fn = logger.info if result.returncode == 0 else logger.error
        log_fn(f"[dnf] {line}")

    if result.returncode == 0:
        logger.info(f"install_system_packages: ok ({len(packages)} package(s))")
    else:
        logger.error(
            f"install_system_packages: dnf exited {result.returncode}; "
            f"projects depending on these packages may fail to start"
        )

async def start_project(cluster: dict[str, Any]) -> None:
    logger.info(f"Starting project: {cluster['project_number']}")

    project_dir = _project_dir(cluster)
    if not project_dir.is_dir():
        logger.error(
            f"Skipping {cluster['project_number']}: project directory missing "
            f"at {project_dir}"
        )
        return

    command = str(cluster.get("run_command") or "").strip()
    if not command:
        logger.error(
            f"Skipping {cluster['project_number']}: empty run_command"
        )
        return

    write_service(cluster, command)

async def stop_project(project_number: str) -> None:
    logger.info(f"Stopping project: {project_number}")
    slug = project_number.replace(" ", "_")
    # teardown 会 -d/-x 并删目录；在线程中跑以免阻塞事件循环
    await asyncio.get_event_loop().run_in_executor(None, teardown_service, slug)

async def cleanup_existing_projects() -> None:
    if not S6_SERVICE_DIR.exists():
        S6_SERVICE_DIR.mkdir(parents=True, exist_ok=True)
        return

    for service_dir in list(S6_SERVICE_DIR.iterdir()):
        if not service_dir.is_dir():
            continue

        if service_dir.name.startswith("."):
            continue
        slug = service_dir.name
        await asyncio.get_event_loop().run_in_executor(None, teardown_service, slug)
        logger.info(f"Cleaned up s6 service: {slug}")
    await rescan_services()

async def start_all_projects(clusters: list[dict[str, Any]]) -> None:
    await asyncio.gather(*(start_project(cluster) for cluster in clusters))
    await rescan_services()

async def stop_all_projects(clusters: list[dict[str, Any]]) -> None:
    logger.info("Stopping all projects...")
    await asyncio.gather(*(stop_project(cluster["project_number"]) for cluster in clusters))
    await rescan_services()
