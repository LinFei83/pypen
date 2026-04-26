from __future__ import annotations

import asyncio
import signal
import sys
from typing import Any

from app.utils.logging_config import logger

from .project_manager import stop_all_projects

def register_signal_handlers(clusters: list[dict[str, Any]]) -> None:

    def _handler(sig, frame):
        logger.info("Shutting down...")
        try:
            asyncio.run(stop_all_projects(clusters))
        except Exception as e:
            logger.error(f"Error while stopping projects on shutdown: {e}")
        sys.exit(0)

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)
