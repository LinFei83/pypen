from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

from loguru import logger

_NOISY_ACCESS_PATHS = re.compile(r'"(GET|POST) (?:/socket\.io/|/service/status)')

class _DropNoisyAccessLogs(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        if _NOISY_ACCESS_PATHS.search(msg):
            return False
        return True

_DEFAULT_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

_configured = False

class InterceptHandler(logging.Handler):

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )

def setup_logging(
    log_file: str | Path = "app.log",
    level: str = "INFO",
    rotation: str = "10 MB",
    retention: int = 5,
) -> None:
    global _configured
    if _configured:
        return

    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format=_DEFAULT_FORMAT,
        colorize=True,
        backtrace=True,
        diagnose=False,
        enqueue=True,
    )
    logger.add(
        str(log_file),
        level=level,
        format=_DEFAULT_FORMAT,
        rotation=rotation,
        retention=retention,
        encoding="utf-8",
        backtrace=True,
        diagnose=False,
        enqueue=True,
    )

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    noise_filter = _DropNoisyAccessLogs()
    for name in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "socketio",
        "engineio",
        "quart.app",
        "quart.serving",
        "asyncio",
        "watchdog",
    ):
        std = logging.getLogger(name)
        std.handlers = [InterceptHandler()]
        std.propagate = False
        std.addFilter(noise_filter)

    for name in ("socketio", "socketio.server", "engineio", "engineio.server"):
        logging.getLogger(name).setLevel(logging.WARNING)

    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("websockets.server").setLevel(logging.WARNING)

    _configured = True

__all__ = ["setup_logging", "InterceptHandler", "logger"]
