import os
import shutil
import subprocess
from typing import Sequence

from app.utils.logging_config import logger

def get_pyenv_python(version: str) -> str:
    major_minor = ".".join(version.split(".")[:2])
    shim = shutil.which(f"python{major_minor}")
    if shim:
        return shim
    logger.warning(
        f"pyenv shim python{major_minor} not found in PATH. Falling back to 'python3'."
    )
    return shutil.which("python3") or "python3"

def run_with_pyenv(version: str, command_args: Sequence[str], **kwargs):
    env = os.environ.copy()
    env["PYENV_VERSION"] = version
    kwargs["env"] = env
    return subprocess.run(command_args, **kwargs)
