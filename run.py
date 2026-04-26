import os
import uvicorn
from app.utils.logging_config import setup_logging, logger
from app import asgi_app

S6_LOG_DIR = "/var/log/s6"

setup_logging(log_file="app.log")

app = asgi_app

if __name__ == "__main__":
    try:
        os.makedirs(S6_LOG_DIR, exist_ok=True)
        port = int(os.environ.get("PORT", 5000))
        uvicorn.run(
            asgi_app,
            host="0.0.0.0",
            port=port,
            log_level="info",
        )
    except Exception as e:
        logger.exception(f"Failed to start application: {e}")
        raise
