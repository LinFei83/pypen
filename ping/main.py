from __future__ import annotations

import sys
import time

from app.utils.logging_config import logger, setup_logging
from worker.config_loader import load_defaults
from worker.constants import CONFIG_FILE, READY_FLAG

from .config import (
    LOG_FILE,
    get_app_url,
    get_ping_interval,
    get_startup_delay,
    normalize_url,
    should_delay_ping,
)
from .services.pinger import ping_loop, wait_for_ready_flag


def run() -> None:
    setup_logging(log_file=LOG_FILE, rotation="10 MB", retention=5)

    defaults = load_defaults(CONFIG_FILE)
    if not defaults.get("ping", True):
        logger.info("Ping disabled via [defaults].ping = false in project.toml; exiting.")
        return

    configured_url = (defaults.get("ping_url") or "").strip()
    app_url = normalize_url(configured_url) if configured_url else get_app_url()
    if not app_url:
        logger.error(
            "No app URL provided. Set the 'APP_URL' environment variable "
            "or pass the URL as a command-line argument."
        )
        sys.exit(1)

    interval = get_ping_interval()

    if should_delay_ping():
        delay = get_startup_delay()
        logger.info(f"Delaying start of pinging by {delay} seconds as per DELAY_PING setting.")
        time.sleep(delay)

    wait_for_ready_flag(READY_FLAG)

    logger.info(f"Starting to ping {app_url} every {interval / 60} minutes...")
    ping_loop(app_url, interval)
