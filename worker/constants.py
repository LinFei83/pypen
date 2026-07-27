from pathlib import Path

LOG_FILE: str = "project_manager.log"
S6_SERVICE_DIR: Path = Path("/etc/s6/services")
S6_LOG_DIR: Path = Path("/var/log/s6")
APP_DIR: Path = Path("/app")
PROJECTS_DIR: Path = APP_DIR / "projects"
CONFIG_FILE: str = "project.toml"
READY_FLAG: Path = Path("/tmp/pypen_ready")
