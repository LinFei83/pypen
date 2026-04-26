from __future__ import annotations

import asyncio
import re
import time

from app.utils.logging_config import logger

from .constants import S6_SERVICE_DIR

_SVSTAT_UP_RE = re.compile(r"^up \(pid (?P<pid>\d+)\) (?P<uptime>\d+) seconds")
_SVSTAT_DOWN_RE = re.compile(r"^down (?P<downtime>\d+) seconds")

async def _run(cmd: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, stdout.decode(), stderr.decode()

async def async_s6_svc(flag: str, service_slug: str) -> None:
    service = str(S6_SERVICE_DIR / service_slug)
    cmd = f"s6-svc {flag} {service}"
    rc, out, err = await _run(cmd)
    if rc != 0:
        logger.error(f"s6-svc command failed ({cmd}): {err.strip() or out.strip()}")
    else:
        logger.info(f"s6-svc command succeeded: {cmd}")

async def rescan_services() -> None:
    logger.info("Rescanning s6 service directory...")
    rc, _, err = await _run(f"s6-svscanctl -a {S6_SERVICE_DIR}")
    if rc != 0:
        logger.error(f"s6-svscanctl failed: {err.strip()}")
    else:
        logger.info("s6 service directory rescanned successfully.")

async def get_process_status(service_slug: str) -> str | None:
    service = str(S6_SERVICE_DIR / service_slug)
    rc, out, _ = await _run(f"s6-svstat {service}")
    if rc != 0:
        return None
    line = out.strip()
    if not line:
        return None
    if line.startswith("up "):
        return "RUNNING"
    if line.startswith("down "):

        if "want up" in line:
            return "BACKOFF"
        return "STOPPED"
    return None

async def wait_for_process_stop(
    service_slug: str, timeout: int = 30, interval: int = 2
) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout:
        status = await get_process_status(service_slug)
        if status != "RUNNING":
            return True
        await asyncio.sleep(interval)
    return False
