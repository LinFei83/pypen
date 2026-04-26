from __future__ import annotations

import sys
from os import path as opath
from subprocess import run as srun

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from app.utils.logging_config import logger, setup_logging

CONFIG_FILE = "project.toml"

if opath.exists("log.txt"):
    with open("log.txt", "r+") as f:
        f.truncate(0)

setup_logging(log_file="log.txt")


def _load_upstream(path: str) -> tuple[str, str]:
    if not opath.exists(path):
        return "", ""
    try:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        logger.error(f"update: TOML parse error in {path}: {exc}")
        return "", ""
    upstream = raw.get("upstream") or {}
    return str(upstream.get("repo") or ""), str(upstream.get("branch") or "main")


UPSTREAM_REPO, UPSTREAM_BRANCH = _load_upstream(CONFIG_FILE)

if UPSTREAM_REPO:
    if opath.exists(".git"):
        srun(["rm", "-rf", ".git"])

    update = srun(
        [
            f"git init -q \
             && git config --global user.email mysteryxdemon@gmail.com \
             && git config --global user.name mysterydemon \
             && git add . \
             && git commit -sm update -q \
             && git remote add origin {UPSTREAM_REPO} \
             && git fetch origin -q \
             && git reset --hard origin/{UPSTREAM_BRANCH} -q"
        ],
        shell=True,
    )

    if update.returncode == 0:
        logger.info("Successfully updated with latest commit from upstream repo")
    else:
        logger.error("Something went wrong while updating; check [upstream] in project.toml")
