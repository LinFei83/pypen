import subprocess
import threading
import time
import os

def run_update():
    subprocess.run(["python3", "update.py"])

def run_uvicorn():
    port = os.environ.get("PORT", "5000")
    subprocess.run(
        ["uvicorn", "run:app", "--host", "0.0.0.0", "--port", port, "--workers", "1"],
        check=True,
    )

def run_s6_svscan():
    os.makedirs("/etc/s6/services", exist_ok=True)
    subprocess.run(["s6-svscan", "/etc/s6/services"])

def run_worker():
    subprocess.run(["python3", "-m", "worker"])

def run_ping_server():
    subprocess.run(["python3", "-m", "ping"])

if __name__ == "__main__":
    update_thread = threading.Thread(target=run_update)
    update_thread.start()
    update_thread.join()
    time.sleep(2)

    uvicorn_thread = threading.Thread(target=run_uvicorn)
    s6_thread = threading.Thread(target=run_s6_svscan)
    worker_thread = threading.Thread(target=run_worker)
    ping_server_thread = threading.Thread(target=run_ping_server)

    uvicorn_thread.start()
    s6_thread.start()
    worker_thread.start()
    ping_server_thread.start()

    uvicorn_thread.join()
    s6_thread.join()
    worker_thread.join()
    ping_server_thread.join()
