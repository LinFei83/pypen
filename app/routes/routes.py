import os
import shutil
import subprocess
import re
import sys
import asyncio
import time
from datetime import datetime
from pathlib import Path
from collections import defaultdict, deque

try:
    import psutil
except Exception:
    psutil = None

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from app import app, sio
from app.utils.logging_config import logger
from quart import (
    render_template, request, jsonify, Response,
)
from werkzeug.exceptions import HTTPException

from worker.constants import PROJECTS_DIR

S6_LOG_DIR = "/var/log/s6"
S6_SERVICE_DIR = "/etc/s6/services"
CONFIG_FILE = Path("/app/project.toml")
STATUS_CHECK_INTERVAL = 2
MAX_STATUS_CHECK_ATTEMPTS = 10

STOPPED_SERVICE_SCRIPTS: dict[str, str] = {}

FAILURE_COUNTS = defaultdict(int)
MAX_FAILURES_BEFORE_PAUSE = 5
PAUSED_BY_SYSTEM = set()

_VALID_NAME_RE = re.compile(r'^[a-zA-Z0-9_\- ]+$')

CPU_HISTORY_LEN = 30
_CPU_HISTORY: dict[str, deque[float]] = defaultdict(
    lambda: deque(maxlen=CPU_HISTORY_LEN)
)

_CPU_PROC_CACHE: dict = {}

_CPU_CORE_COUNT = max(1, (os.cpu_count() or 1))

def _sample_cpu(process_name: str, pid: str | int | None) -> float | None:
    if psutil is None or pid in (None, "", "-"):
        return None
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        return None
    proc = _CPU_PROC_CACHE.get(pid_int)
    try:
        if proc is None or not proc.is_running() or proc.pid != pid_int:
            proc = psutil.Process(pid_int)
            _CPU_PROC_CACHE[pid_int] = proc

            proc.cpu_percent(interval=None)
            cpu = 0.0
        else:
            cpu = float(proc.cpu_percent(interval=None))
    except (psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError):
        _CPU_PROC_CACHE.pop(pid_int, None)
        return None
    except Exception:
        return None

    cpu_norm = max(0.0, min(100.0, cpu / _CPU_CORE_COUNT))
    _CPU_HISTORY[process_name].append(cpu_norm)
    return cpu_norm

def _cpu_history_for(process_name: str) -> list[float]:
    history = _CPU_HISTORY.get(process_name)
    return [round(v, 2) for v in history] if history else []

def _slug(process_name: str) -> str:
    return process_name.replace(" ", "_")

def _project_workdir(process_name: str) -> Path:
    return PROJECTS_DIR / _slug(process_name)

def _svc_path(process_name: str) -> Path:
    return Path(S6_SERVICE_DIR) / _slug(process_name)

def _run_cmd(cmd: list[str], timeout: int = 30, quiet: bool = False) -> dict:
    log = logger.debug if quiet else logger.info
    err_log = logger.debug if quiet else logger.error
    try:
        log(f"Executing: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.stdout:
            log(f"Command output: {result.stdout.strip()}")
        if result.stderr and result.returncode != 0:
            err_log(f"Command error: {result.stderr.strip()}")
        if result.returncode == 0:
            return {"status": "success", "message": result.stdout.strip()}
        return {"status": "error", "message": (result.stderr or result.stdout).strip()}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": f"命令在 {timeout} 秒后超时"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def s6_svstat(process_name: str) -> dict | None:
    svc = _svc_path(process_name)
    if not svc.is_dir():
        return None
    res = _run_cmd(["s6-svstat", str(svc)], timeout=5, quiet=True)
    if res["status"] != "success":
        return None
    line = res["message"]
    pid_match = re.search(r'pid (\d+)', line)
    pid = pid_match.group(1) if pid_match else None
    uptime_match = re.search(r'(\d+) seconds', line)
    uptime_seconds = int(uptime_match.group(1)) if uptime_match else 0

    if line.startswith("up "):
        status = "RUNNING"
    elif line.startswith("down "):
        status = "BACKOFF" if "want up" in line else "STOPPED"
    else:
        status = "UNKNOWN"

    # s6-svstat 在 SIGSTOP 时会带 ", paused"；同时用 /proc State 兜底
    paused = (", paused" in line) or (bool(pid) and is_process_paused(pid))

    hours, rem = divmod(uptime_seconds, 3600)
    minutes, secs = divmod(rem, 60)
    uptime = f"{hours}:{minutes:02d}:{secs:02d}"

    cpu_pct: float | None = None
    if status == "RUNNING" and pid and not paused:
        cpu_pct = _sample_cpu(process_name, pid)
    cpu_history = _cpu_history_for(process_name)

    return {
        "name": process_name,
        "status": status,
        "pid": pid,
        "uptime": uptime,
        "paused": paused,
        "cpu": round(cpu_pct, 2) if cpu_pct is not None else None,
        "cpu_history": cpu_history,
    }

def list_services() -> list[str]:
    try:
        return sorted(
            p.name for p in Path(S6_SERVICE_DIR).iterdir()
            if p.is_dir() and not p.name.startswith('.')
        )
    except FileNotFoundError:
        return []

def _configured_project_ids() -> list[str]:
    try:
        with CONFIG_FILE.open("rb") as fh:
            raw = tomllib.load(fh)
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return []
    projects = raw.get("project") or []
    if not isinstance(projects, list):
        return []
    out: list[str] = []
    for entry in projects:
        if not isinstance(entry, dict):
            continue
        pid = str(entry.get("id", "")).strip()
        if pid:
            out.append(pid)
    return out

def _placeholder_for(raw_id: str) -> dict:
    return {
        "name": raw_id,
        "status": "PENDING",
        "pid": None,
        "uptime": "0:00:00",
        "paused": False,
        "auto_paused": False,
        "cpu": None,
        "cpu_history": [],
    }

_HEAL_COOLDOWN: dict[str, float] = {}
_HEAL_COOLDOWN_SEC = 30.0

def _heal_stale_supervise(process_name: str, *, force: bool = False) -> dict | None:
    """僵死 supervise/ 会导致 svstat 失败却仍有日志。删掉 supervise 后 rescan 重建。"""
    svc = _svc_path(process_name)
    supervise = svc / "supervise"
    if not svc.is_dir() or not supervise.exists():
        return None
    now = time.monotonic()
    last = _HEAL_COOLDOWN.get(process_name, 0.0)
    if not force and now - last < _HEAL_COOLDOWN_SEC:
        return None
    _HEAL_COOLDOWN[process_name] = now
    logger.warning(f"Healing stale supervise for {process_name}")
    _run_cmd(["s6-svc", "-x", str(svc)], timeout=5, quiet=True)
    log_svc = svc / "log"
    if log_svc.is_dir():
        _run_cmd(["s6-svc", "-x", str(log_svc)], timeout=5, quiet=True)
    for stale in (log_svc / "supervise", supervise):
        if stale.exists():
            shutil.rmtree(stale, ignore_errors=True)
    s6_rescan()
    return s6_svstat(process_name)

def _collect_processes() -> list[dict]:
    configured = set(_configured_project_ids())
    services = list_services()
    processes: list[dict] = []
    needs_rescan = False
    for name in services:
        # 取消登记后残留的 s6 目录不再展示为设备卡片
        if name not in configured:
            continue
        parsed = s6_svstat(name)
        if not parsed:
            healed = _heal_stale_supervise(name)
            if healed:
                parsed = healed
            else:
                needs_rescan = True
                processes.append({
                    "name": name,
                    "status": "PENDING",
                    "pid": None,
                    "uptime": "0:00:00",
                    "paused": False,
                    "auto_paused": False,
                    "cpu": None,
                    "cpu_history": [],
                })
                continue
        pname = parsed["name"]
        if parsed["status"] == "BACKOFF":
            FAILURE_COUNTS[pname] += 1
            if FAILURE_COUNTS[pname] >= MAX_FAILURES_BEFORE_PAUSE and pname not in PAUSED_BY_SYSTEM:
                logger.warning(
                    f"Process {pname} has failed {FAILURE_COUNTS[pname]} times, auto-pausing"
                )
                PAUSED_BY_SYSTEM.add(pname)
                s6_svc("-d", pname)
            parsed["auto_paused"] = pname in PAUSED_BY_SYSTEM
        else:
            if parsed["status"] == "RUNNING":
                FAILURE_COUNTS[pname] = 0
                PAUSED_BY_SYSTEM.discard(pname)
            parsed["auto_paused"] = pname in PAUSED_BY_SYSTEM
        processes.append(parsed)

    if needs_rescan:
        s6_rescan()

    known = {p["name"] for p in processes}
    for raw_id in configured:
        if raw_id in known:
            continue
        processes.append(_placeholder_for(raw_id))

    return processes

def s6_rescan() -> None:
    _run_cmd(["s6-svscanctl", "-a", S6_SERVICE_DIR], timeout=5, quiet=True)

def s6_svc(flag: str, process_name: str) -> dict:
    svc = _svc_path(process_name)
    if not svc.is_dir():
        return {"status": "error", "message": f"未找到服务 {process_name}"}
    return _run_cmd(["s6-svc", flag, str(svc)], timeout=10)

def is_process_paused(pid) -> bool:
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("State:") and "\tT" in line:
                    return True
    except Exception:
        pass
    return False

def pause_process(process_name: str) -> dict:
    result = s6_svc("-p", process_name)

    workdir = _project_workdir(process_name)
    try:
        subprocess.run(
            ["pkill", "-STOP", "-f", str(workdir)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception as exc:
        logger.debug(f"pause_process({process_name}) pkill failed: {exc}")
    if result["status"] == "success":
        return {"status": "success", "message": f"已暂停进程 {process_name}"}
    return {"status": "error", "message": result["message"]}

def resume_process(process_name: str) -> dict:
    result = s6_svc("-c", process_name)
    workdir = _project_workdir(process_name)
    try:
        subprocess.run(
            ["pkill", "-CONT", "-f", str(workdir)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception as exc:
        logger.debug(f"resume_process({process_name}) pkill failed: {exc}")
    if result["status"] == "success":
        return {"status": "success", "message": f"已恢复进程 {process_name}"}
    return {"status": "error", "message": result["message"]}

async def broadcast_status_update() -> bool:
    try:
        await sio.emit('status_update', {
            "status": "success",
            "processes": _collect_processes(),
            "timestamp": datetime.utcnow().isoformat()
        })
        return True
    except Exception as e:
        logger.error(f"Error broadcasting status update: {str(e)}")
        return False

def _truthy(val) -> bool:
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in {"true", "yes", "1", "on"}

def _pull_commits_enabled(process_name: str) -> bool:
    project = _find_project_config(process_name)
    if not project:
        return False
    cron = project.get("cron") or {}
    if not isinstance(cron, dict):
        return False
    return _truthy(cron.get("pull_commits"))

def update_process_code(process_name: str) -> None:
    workdir = _project_workdir(process_name)
    if not workdir.exists():
        logger.warning(f"git pull skipped for {process_name}: no working directory")
        return

    if not _pull_commits_enabled(process_name):
        logger.info(
            f"git pull skipped for {process_name}: pull_commits is not 'true' in project.toml"
        )
        return

    try:
        _git_pull_workdir(process_name, workdir)
    except Exception as exc:
        logger.error(f"git pull during start/restart failed for {process_name}: {exc}")

def _git_pull_workdir(process_name: str, workdir: Path) -> None:
    """在项目目录执行 git pull --ff-only；失败时抛出异常。"""
    if not (workdir / ".git").exists():
        raise RuntimeError(f"{process_name} 不是 git 仓库，无法同步代码")

    logger.info(f"git pull starting for {process_name} in {workdir}")
    try:
        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error(f"git pull timed out for {process_name}")
        raise RuntimeError(f"git pull 超时：{process_name}") from exc
    except Exception as e:
        logger.error(f"git pull failed for {process_name}: {e}")
        raise

    for line in (result.stdout or "").splitlines():
        logger.info(f"[git pull {process_name}] {line}")
    for line in (result.stderr or "").splitlines():
        log_fn = logger.info if result.returncode == 0 else logger.error
        log_fn(f"[git pull {process_name}] {line}")

    if result.returncode == 0:
        logger.info(f"git pull finished for {process_name}")
        return

    detail = (result.stderr or result.stdout or "").strip() or f"exit {result.returncode}"
    raise RuntimeError(f"git pull 失败（{process_name}）：{detail}")

_PROJECT_CFG_LOCK: asyncio.Lock | None = None

def _project_cfg_lock() -> asyncio.Lock:
    global _PROJECT_CFG_LOCK
    if _PROJECT_CFG_LOCK is None:
        _PROJECT_CFG_LOCK = asyncio.Lock()
    return _PROJECT_CFG_LOCK

@app.route('/')
async def cluster():
    return await render_template('cluster.html')

@app.route('/service/status', methods=['GET'])
async def list_service_processes():
    return jsonify({"status": "success", "processes": _collect_processes()}), 200

@app.route('/service/pause/<process_name>', methods=['POST'])
async def pause_service_process(process_name):
    logger.info(f"Received pause request for process: {process_name}")
    if not _VALID_NAME_RE.match(process_name):
        return jsonify({"status": "error", "message": "无效的进程名称"}), 400
    result = pause_process(process_name)
    if result["status"] == "success":
        await broadcast_status_update()
        return jsonify(result), 200
    return jsonify(result), 500

@app.route('/service/resume/<process_name>', methods=['POST'])
async def resume_service_process(process_name):
    logger.info(f"Received resume request for process: {process_name}")
    if not _VALID_NAME_RE.match(process_name):
        return jsonify({"status": "error", "message": "无效的进程名称"}), 400
    result = resume_process(process_name)
    if result["status"] == "success":
        await broadcast_status_update()
        return jsonify(result), 200
    return jsonify(result), 500

@sio.event
async def connect(sid, environ, auth=None):
    logger.debug(f"Client connected: {sid}")
    await sio.emit('connected', {'data': 'Connected'}, to=sid)
    await broadcast_status_update()

@sio.event
async def disconnect(sid):
    logger.debug(f"Client disconnected: {sid}")

@sio.on('request_status')
async def handle_status_request(sid):
    try:
        processes = _collect_processes()
        if not processes:
            logger.warning("No projects configured and no s6 services found")
        await sio.emit('status_update', {
            "status": "success",
            "processes": processes,
            "timestamp": datetime.utcnow().isoformat()
        }, to=sid)
    except Exception as e:
        logger.error(f"Error in handle_status_request: {str(e)}")
        await sio.emit('status_update', {
            "status": "error",
            "message": str(e),
            "processes": []
        }, to=sid)

def _save_and_unlink_run(process_name: str) -> None:
    run_path = _svc_path(process_name) / "run"
    if run_path.exists():
        STOPPED_SERVICE_SCRIPTS[process_name] = run_path.read_text()
        run_path.unlink()

def _restore_run(process_name: str) -> bool:
    if process_name not in STOPPED_SERVICE_SCRIPTS:
        return False
    run_path = _svc_path(process_name) / "run"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text(STOPPED_SERVICE_SCRIPTS[process_name])
    run_path.chmod(0o755)
    del STOPPED_SERVICE_SCRIPTS[process_name]
    return True

async def _wait_for_status(process_name: str, expected: str | None) -> bool:
    for _ in range(MAX_STATUS_CHECK_ATTEMPTS):
        await asyncio.sleep(STATUS_CHECK_INTERVAL)
        parsed = s6_svstat(process_name)
        if expected is None:
            if parsed is None or parsed["status"] != "RUNNING":
                return True
        else:
            if parsed and parsed["status"] == expected:
                return True
    return False

async def _wait_for_supervise(process_name: str, attempts: int = 15) -> bool:
    """rescan 后等待 s6-supervise 监听，便于后续 s6-svc / svstat。"""
    for _ in range(attempts):
        parsed = s6_svstat(process_name)
        if parsed is not None:
            return True
        await asyncio.sleep(0.4)
    return False

@app.route('/service/<action>/<process_name>', methods=['POST'])
async def manage_service_process(action, process_name):
    logger.info(f"Received {action} request for process: {process_name}")

    if action not in ("start", "stop", "restart"):
        return jsonify({"status": "error", "message": "无效的操作"}), 400

    if not _VALID_NAME_RE.match(process_name):
        return jsonify({"status": "error", "message": "无效的进程名称"}), 400

    parsed = s6_svstat(process_name)
    if parsed is None and action != "start":
        return jsonify({
            "status": "error",
            "message": f"未找到进程 {process_name}"
        }), 404

    try:
        if action == "stop":
            if parsed["status"] != "RUNNING":
                return jsonify({
                    "status": "error",
                    "message": f"进程 {process_name} 未在运行"
                }), 400

            result = _run_cmd(
                ["s6-svc", "-wD", "-d", str(_svc_path(process_name))],
                timeout=15,
            )
            _kill_orphans(process_name)
            if result["status"] == "success":
                _save_and_unlink_run(process_name)
                s6_rescan()
            expected = None

        elif action == "start":
            if not _restore_run(process_name) and not (_svc_path(process_name) / "run").exists():
                return jsonify({
                    "status": "error",
                    "message": f"服务 {process_name} 没有运行脚本"
                }), 404
            # 先清孤儿，避免端口占用导致反复退出却仍有日志
            _kill_orphans(process_name)
            update_process_code(process_name)
            s6_rescan()
            # 僵死 supervise 时先自愈，再等待就绪后启动
            if s6_svstat(process_name) is None:
                _heal_stale_supervise(process_name, force=True)
            await _wait_for_supervise(process_name)
            PAUSED_BY_SYSTEM.discard(process_name)
            FAILURE_COUNTS[process_name] = 0
            result = s6_svc("-u", process_name)
            expected = "RUNNING"

        else:
            thoroughly_cleanup(process_name)
            delete_service_logs(process_name)
            update_process_code(process_name)
            result = s6_svc("-r", process_name)
            expected = "RUNNING"

        if result["status"] != "success":
            return jsonify(result), 500

        if await _wait_for_status(process_name, expected):
            await broadcast_status_update()
            action_labels = {"start": "启动", "stop": "停止", "restart": "重启"}
            label = action_labels.get(action, action)
            msg = f"已成功{label} {process_name}"
            return jsonify({"status": "success", "message": msg}), 200

        return jsonify({
            "status": "error",
            "message": f"执行「{action}」后进程未达到预期状态"
        }), 500

    except Exception as e:
        logger.error(f"Error managing process {process_name}: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"管理进程时出错：{str(e)}"
        }), 500

@app.route('/service/log/<process_name>', methods=['GET'])
async def download_service_log(process_name):
    try:
        if not _VALID_NAME_RE.match(process_name):
            return jsonify({"status": "error", "message": "无效的进程名称"}), 400

        log_file = Path(S6_LOG_DIR) / _slug(process_name) / "current"
        if not log_file.exists():
            return jsonify({
                "status": "error",
                "message": "未找到该进程的日志文件"
            }), 404

        try:
            data = log_file.read_bytes()
        except OSError as exc:
            logger.error(f"Error reading log file for {process_name}: {exc}")
            return jsonify({"status": "error", "message": str(exc)}), 500

        download_name = f"{process_name}_log.txt"
        return Response(
            data,
            mimetype="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{download_name}"',
                "Cache-Control": "no-store",
            },
        )

    except Exception as e:
        logger.error(f"Error accessing log file for {process_name}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.errorhandler(Exception)
async def handle_error(e):
    try:
        req_info = f"{request.method} {request.path} from {request.remote_addr}"
        ua = request.headers.get("User-Agent", "")
        if ua:
            req_info += f" ua={ua!r}"
    except Exception:
        req_info = "<no request context>"

    if isinstance(e, HTTPException):
        status = e.code or 500
        if status >= 500:
            logger.error(f"HTTP {status} [{req_info}]: {e}")
        else:
            logger.info(f"HTTP {status} [{req_info}]: {e}")
        return jsonify({
            "status": "error",
            "message": e.description or e.name,
        }), status

    logger.error(f"Unhandled error [{req_info}]: {str(e)}")
    return jsonify({
        "status": "error",
        "message": "服务器内部错误"
    }), 500

def delete_service_logs(process_name: str) -> None:
    log_svc = _svc_path(process_name) / "log"
    log_svc_active = log_svc.is_dir()
    try:
        if log_svc_active:

            _run_cmd(
                ["s6-svc", "-wD", "-d", str(log_svc)],
                timeout=10,
                quiet=True,
            )
    except Exception as e:
        logger.warning(f"Could not stop log service for {process_name}: {e}")

    try:
        log_dir = Path(S6_LOG_DIR) / _slug(process_name)
        if log_dir.exists():
            for f in log_dir.iterdir():
                try:
                    f.unlink()
                    logger.info(f"Deleted log file: {f}")
                except Exception as e:
                    logger.error(f"Failed to delete {f}: {e}")
    except Exception as e:
        logger.error(f"Error deleting logs for {process_name}: {e}")
    finally:
        if log_svc_active:
            try:

                _run_cmd(["s6-svc", "-u", str(log_svc)], timeout=5, quiet=True)
            except Exception as e:
                logger.warning(
                    f"Could not restart log service for {process_name}: {e}"
                )

def _kill_orphans(process_name: str) -> None:
    workdir = _project_workdir(process_name)
    workdir_resolved = str(workdir.resolve()) if workdir.exists() else str(workdir)
    patterns = [workdir_resolved, str(workdir)]

    for pat in patterns:
        try:
            subprocess.run(
                ["pkill", "-9", "-f", pat],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except Exception as exc:
            logger.debug(f"_kill_orphans({process_name}) pkill {pat} failed: {exc}")

    # pkill -f 只匹配命令行；项目进程 argv 可能不含路径，再按 cwd 清理
    try:
        for proc_dir in Path("/proc").iterdir():
            if not proc_dir.name.isdigit():
                continue
            try:
                cwd = (proc_dir / "cwd").resolve()
            except OSError:
                continue
            if str(cwd) != workdir_resolved and not str(cwd).startswith(workdir_resolved + "/"):
                continue
            pid = int(proc_dir.name)
            try:
                # 跳过本进程
                if pid == os.getpid():
                    continue
                os.kill(pid, 9)
                logger.info(f"_kill_orphans({process_name}): killed pid {pid} cwd={cwd}")
            except OSError:
                pass
    except Exception as exc:
        logger.debug(f"_kill_orphans({process_name}) /proc scan failed: {exc}")

def thoroughly_cleanup(process_name: str) -> None:
    _kill_orphans(process_name)
    workdir = _project_workdir(process_name)
    if workdir.exists():
        for root, dirs, files in os.walk(workdir):
            for d in dirs:
                if d == '__pycache__':
                    pycache_dir = Path(root) / d
                    for file in pycache_dir.glob('*.pyc'):
                        file.unlink()
                    try:
                        pycache_dir.rmdir()
                    except OSError:
                        pass
            for f in files:
                if f.endswith('.pyc'):
                    (Path(root) / f).unlink()

@app.route('/service/clear_failure/<process_name>', methods=['POST'])
async def clear_failure(process_name):
    if not _VALID_NAME_RE.match(process_name):
        return jsonify({"status": "error", "message": "无效的进程名称"}), 400
    FAILURE_COUNTS[process_name] = 0
    PAUSED_BY_SYSTEM.discard(process_name)
    s6_svc("-u", process_name)
    await broadcast_status_update()
    return jsonify({"status": "success", "message": f"已清除 {process_name} 的失败状态"})

def _find_project_config(process_name: str) -> dict | None:
    try:
        with CONFIG_FILE.open("rb") as fh:
            raw = tomllib.load(fh)
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return None
    projects = raw.get("project") or []
    if not isinstance(projects, list):
        return None
    for entry in projects:
        if not isinstance(entry, dict):
            continue
        raw_id = str(entry.get("id", "")).strip()
        if not raw_id:
            continue
        if process_name == raw_id:
            merged = dict(entry)
            merged["_raw_id"] = raw_id
            return merged
    return None

def _redeploy_blocking(process_name: str, project: dict | None = None) -> None:
    """本地模式：仅在项目目录 git pull，不删目录、不重新 clone、不重建 venv。"""
    del project  # 保留签名以兼容 cron 调用
    workdir = _project_workdir(process_name)
    if not workdir.is_dir():
        raise RuntimeError(f"项目目录不存在：{workdir}")
    _git_pull_workdir(process_name, workdir)

@app.route('/service/redeploy/<process_name>', methods=['POST'])
async def redeploy_service(process_name):
    logger.info(f"Received sync-code request for process: {process_name}")
    if not _VALID_NAME_RE.match(process_name):
        return jsonify({"status": "error", "message": "无效的进程名称"}), 400

    parsed = s6_svstat(process_name)
    if parsed is None:
        return jsonify({"status": "error", "message": f"未找到服务 {process_name}"}), 404

    project = _find_project_config(process_name)
    if project is None:
        return jsonify({
            "status": "error",
            "message": f"project.toml 中没有与 {process_name} 匹配的条目",
        }), 404

    try:
        _run_cmd(
            ["s6-svc", "-wD", "-d", str(_svc_path(process_name))],
            timeout=15,
        )
        _kill_orphans(process_name)
        await _wait_for_status(process_name, None)

        await asyncio.get_event_loop().run_in_executor(
            None, _redeploy_blocking, process_name, project
        )

        FAILURE_COUNTS[process_name] = 0
        PAUSED_BY_SYSTEM.discard(process_name)
        delete_service_logs(process_name)
        s6_rescan()
        result = s6_svc("-u", process_name)
        if result["status"] != "success":
            return jsonify(result), 500

        if await _wait_for_status(process_name, "RUNNING"):
            await broadcast_status_update()
            return jsonify({
                "status": "success",
                "message": f"已重新同步代码并启动 {process_name}",
            }), 200
        return jsonify({
            "status": "error",
            "message": "同步代码后服务未进入运行状态",
        }), 500
    except Exception as e:
        logger.exception(f"Sync code failed for {process_name}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/service/stream-view/<process_name>')
async def stream_log_page(process_name):
    if not _VALID_NAME_RE.match(process_name):
        return jsonify({"status": "error", "message": "无效的进程名称"}), 400
    return await render_template("log_stream.html", process_name=process_name)

@app.route('/service/stream/<process_name>')
async def stream_service_log(process_name):
    if not _VALID_NAME_RE.match(process_name):
        return jsonify({"status": "error", "message": "无效的进程名称"}), 400

    log_file = Path(S6_LOG_DIR) / _slug(process_name) / "current"

    async def _tail():

        yield f"data: [stream] 已连接到 {process_name}\n\n"
        if not log_file.exists():
            yield f"data: [stream] 等待日志文件 {log_file} 出现…\n\n"
        else:
            yield f"data: [stream] 正在跟踪 {log_file}\n\n"

        fh = None
        inode = None
        try:
            while True:
                try:
                    if not log_file.exists():
                        if fh is not None:
                            try:
                                fh.close()
                            except Exception:
                                pass
                            fh = None
                            inode = None
                        await asyncio.sleep(1.0)

                        yield ": waiting-for-log\n\n"
                        continue

                    st = log_file.stat()
                    if fh is None or inode != st.st_ino:

                        if fh is not None:
                            try:
                                fh.close()
                            except Exception:
                                pass
                        fh = log_file.open("r", encoding="utf-8", errors="replace")
                        fh.seek(0, os.SEEK_END)
                        inode = st.st_ino

                    chunk = fh.read()
                    if chunk:
                        for line in chunk.splitlines():
                            yield f"data: {line}\n\n"
                    else:

                        yield ": ping\n\n"
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(
                        f"stream_service_log({process_name}) tail error: {exc}"
                    )
                    yield f"data: [stream] 错误：{exc}\n\n"
                    if fh is not None:
                        try:
                            fh.close()
                        except Exception:
                            pass
                        fh = None
                        inode = None
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            return
        finally:
            if fh is not None:
                try:
                    fh.close()
                except Exception:
                    pass

    headers = {

        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return Response(_tail(), headers=headers, mimetype="text/event-stream")


def _normalize_api_entry(payload: dict, *, project_id: str | None = None) -> dict:
    pid = str(project_id or payload.get("id") or "").strip()
    cron_in = payload.get("cron") if isinstance(payload.get("cron"), dict) else {}
    env_in = payload.get("env") if isinstance(payload.get("env"), dict) else {}
    return {
        "id": pid,
        "run_command": str(payload.get("run_command") or "").strip(),
        "logs_size": str(payload.get("logs_size") or "10M").strip() or "10M",
        "env": {str(k): str(v) for k, v in env_in.items()},
        "cron": {
            "restart_on": str(cron_in.get("restart_on", "0")),
            "redeploy": str(cron_in.get("redeploy", "false")).lower(),
            "idle": str(cron_in.get("idle", "")),
            "pull_commits": str(cron_in.get("pull_commits", "false")).lower(),
        },
    }

async def _apply_project_service(entry: dict, *, start: bool = True) -> None:
    from worker.s6_config import write_service
    from worker.toml_store import entry_to_cluster

    cluster = entry_to_cluster(entry)
    command = cluster["run_command"]
    write_service(cluster, command)
    s6_rescan()
    # 等 supervise 就绪后再 -u，避免「supervise not listening」
    await _wait_for_supervise(cluster["id"])
    if start:
        _restore_run(cluster["id"])
        s6_svc("-u", cluster["id"])
        await _wait_for_status(cluster["id"], "RUNNING")

async def _unapply_project_service(project_id: str) -> None:
    from worker.s6_config import teardown_service

    slug = _slug(project_id)
    svc = _svc_path(slug)
    if svc.is_dir():
        _kill_orphans(slug)
        await asyncio.get_event_loop().run_in_executor(None, teardown_service, slug)
        STOPPED_SERVICE_SCRIPTS.pop(slug, None)
    s6_rescan()

@app.route("/api/projects", methods=["GET"])
async def api_list_projects():
    from worker.toml_store import list_project_dirs, read_raw_projects

    dirs = list_project_dirs()
    registered = {p["id"]: p for p in read_raw_projects()}
    services = set(list_services())
    items = []
    for name in dirs:
        conf = registered.get(name)
        status = None
        if name in services:
            parsed = s6_svstat(name)
            status = parsed["status"] if parsed else "PENDING"
        elif conf:
            status = "PENDING"
        items.append(
            {
                "id": name,
                "registered": conf is not None,
                "has_dir": True,
                "run_command": (conf or {}).get("run_command", ""),
                "logs_size": (conf or {}).get("logs_size", "10M"),
                "env": (conf or {}).get("env") or {},
                "cron": (conf or {}).get("cron") or {},
                "service_status": status,
            }
        )
    # toml 中有登记但目录缺失的也列出
    for pid, conf in registered.items():
        if pid in dirs:
            continue
        items.append(
            {
                "id": pid,
                "registered": True,
                "has_dir": False,
                "run_command": conf.get("run_command", ""),
                "logs_size": conf.get("logs_size", "10M"),
                "env": conf.get("env") or {},
                "cron": conf.get("cron") or {},
                "service_status": None,
            }
        )
    items.sort(key=lambda x: x["id"].lower())
    return jsonify({"status": "success", "projects": items})

@app.route("/api/projects", methods=["POST"])
async def api_create_project():
    from worker.toml_store import upsert_project, validate_entry
    from app.cron import reload_cron_tasks

    payload = await request.get_json(force=True, silent=True) or {}
    entry = _normalize_api_entry(payload)
    err = validate_entry(entry, require_dir=True)
    if err:
        return jsonify({"status": "error", "message": err}), 400

    async with _project_cfg_lock():
        try:
            await asyncio.get_event_loop().run_in_executor(None, upsert_project, entry)
            await _apply_project_service(entry, start=True)
            await reload_cron_tasks()
        except Exception as exc:
            logger.exception(f"api_create_project failed: {exc}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    await broadcast_status_update()
    return jsonify({
        "status": "success",
        "message": f"已启用项目 {entry['id']}",
        "project": entry,
    })

@app.route("/api/projects/<project_id>", methods=["PUT"])
async def api_update_project(project_id):
    from worker.toml_store import read_raw_projects, upsert_project, validate_entry
    from app.cron import reload_cron_tasks

    if not _VALID_NAME_RE.match(project_id):
        return jsonify({"status": "error", "message": "无效的项目名称"}), 400

    known = {p["id"] for p in read_raw_projects()}
    if project_id not in known:
        return jsonify({"status": "error", "message": f"未登记项目：{project_id}"}), 404

    payload = await request.get_json(force=True, silent=True) or {}
    entry = _normalize_api_entry(payload, project_id=project_id)
    err = validate_entry(entry, require_dir=True)
    if err:
        return jsonify({"status": "error", "message": err}), 400

    async with _project_cfg_lock():
        try:
            # 更新 run 脚本前先停服务，避免半更新
            await _unapply_project_service(project_id)
            await asyncio.get_event_loop().run_in_executor(None, upsert_project, entry)
            await _apply_project_service(entry, start=True)
            await reload_cron_tasks()
        except Exception as exc:
            logger.exception(f"api_update_project failed: {exc}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    await broadcast_status_update()
    return jsonify({
        "status": "success",
        "message": f"已更新项目 {project_id}",
        "project": entry,
    })

@app.route("/api/projects/<project_id>", methods=["DELETE"])
async def api_delete_project(project_id):
    from worker.toml_store import remove_project
    from app.cron import reload_cron_tasks

    if not _VALID_NAME_RE.match(project_id):
        return jsonify({"status": "error", "message": "无效的项目名称"}), 400

    async with _project_cfg_lock():
        try:
            await _unapply_project_service(project_id)
            removed = await asyncio.get_event_loop().run_in_executor(
                None, remove_project, project_id
            )
            if not removed:
                return jsonify({
                    "status": "error",
                    "message": f"project.toml 中没有 {project_id}",
                }), 404
            await reload_cron_tasks()
        except Exception as exc:
            logger.exception(f"api_delete_project failed: {exc}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    await broadcast_status_update()
    return jsonify({
        "status": "success",
        "message": f"已取消登记 {project_id}（未删除 projects/{project_id}/）",
    })
