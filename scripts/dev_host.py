from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = REPO_ROOT / ".run"
STATE_PATH = RUN_DIR / "browser_host.json"
LOG_PATH = RUN_DIR / "browser_host.log"
DEFAULT_SCENARIO = "scenarios/ship_duel.toml"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the current browser host")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Start the browser host")
    start.add_argument("scenario", nargs="?", default=DEFAULT_SCENARIO)
    start.add_argument("--host", default=DEFAULT_HOST)
    start.add_argument("--port", type=int, default=DEFAULT_PORT)

    subparsers.add_parser("stop", help="Stop the browser host")
    subparsers.add_parser("status", help="Show browser host status")

    args = parser.parse_args()

    if args.command == "start":
        return start_host(args.scenario, args.host, args.port)
    if args.command == "stop":
        return stop_host()
    return show_status()


def start_host(scenario: str, host: str, port: int) -> int:
    state = load_state()
    if state is not None:
        status = tracked_status(state)
        if status == "running":
            print_running(state)
            return 0
        if status == "ambiguous":
            print(
                "Refusing to start: the saved PID is still alive but the tracked port is closed."
            )
            print(f"State: {STATE_PATH}")
            return 1
        if status == "port_busy":
            print("Refusing to start: the tracked port is already in use by another process.")
            print(f"State: {STATE_PATH}")
            return 1
        STATE_PATH.unlink(missing_ok=True)

    if port_in_use(host, port):
        print(f"Refusing to start: {host}:{port} is already in use.")
        return 1

    RUN_DIR.mkdir(parents=True, exist_ok=True)

    scenario_path = (REPO_ROOT / scenario).resolve()
    command = [
        sys.executable,
        "-m",
        "tac_sandbox.web_host",
        str(scenario_path),
        "--host",
        host,
        "--port",
        str(port),
    ]

    with LOG_PATH.open("w", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=os.name != "nt",
            creationflags=windows_creationflags(),
        )

    state = {
        "pid": process.pid,
        "host": host,
        "port": port,
        "scenario": str(scenario_path),
        "log_path": str(LOG_PATH),
    }
    save_state(state)

    if not wait_for_port(host, port, timeout_seconds=5.0):
        if process_exists(process.pid):
            terminate_process(process.pid)
        STATE_PATH.unlink(missing_ok=True)
        print("Browser host failed to start.")
        print(f"Log: {LOG_PATH}")
        return 1

    print_running(state)
    return 0


def stop_host() -> int:
    state = load_state()
    if state is None:
        print("No managed browser host is running.")
        return 0

    status = tracked_status(state)
    if status == "stale":
        STATE_PATH.unlink(missing_ok=True)
        print("Removed stale browser host state.")
        return 0

    if status == "port_busy":
        print("Refusing to stop: the tracked port is busy but the saved PID is gone.")
        print(f"State: {STATE_PATH}")
        return 1

    if status == "ambiguous":
        print(
            "Refusing to stop: the saved PID is alive but the tracked port is closed."
        )
        print(f"State: {STATE_PATH}")
        return 1

    pid = int(state["pid"])
    if not terminate_process(pid):
        print(f"Failed to stop browser host pid {pid}.")
        return 1

    STATE_PATH.unlink(missing_ok=True)

    host = str(state["host"])
    port = int(state["port"])
    if wait_for_port_release(host, port, timeout_seconds=5.0):
        print(f"Stopped browser host on http://{host}:{port}")
        return 0

    print(f"Browser host process stopped, but {host}:{port} is still in use.")
    return 1


def show_status() -> int:
    state = load_state()
    if state is None:
        print("Browser host is stopped.")
        return 0

    status = tracked_status(state)
    if status == "running":
        print_running(state)
        return 0
    if status == "stale":
        print("Browser host is stopped, but stale state is present.")
        print(f"State: {STATE_PATH}")
        return 0
    if status == "port_busy":
        print("Tracked state is stale and the tracked port is occupied.")
        print(f"State: {STATE_PATH}")
        return 1

    print("Tracked state is ambiguous.")
    print(f"State: {STATE_PATH}")
    return 1


def print_running(state: dict) -> None:
    print(
        f"Browser host running on http://{state['host']}:{state['port']} "
        f"(pid {state['pid']})"
    )
    print(f"Scenario: {state['scenario']}")
    print(f"Log: {state['log_path']}")


def load_state() -> dict | None:
    if not STATE_PATH.exists():
        return None
    with STATE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_state(state: dict) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    with STATE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)


def tracked_status(state: dict) -> str:
    pid = int(state["pid"])
    host = str(state["host"])
    port = int(state["port"])

    pid_alive = process_exists(pid)
    port_open = port_in_use(host, port)

    if pid_alive and port_open:
        return "running"
    if pid_alive and not port_open:
        return "ambiguous"
    if not pid_alive and port_open:
        return "port_busy"
    return "stale"


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def wait_for_port(host: str, port: int, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if port_in_use(host, port):
            return True
        time.sleep(0.1)
    return False


def wait_for_port_release(host: str, port: int, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not port_in_use(host, port):
            return True
        time.sleep(0.1)
    return False


def terminate_process(pid: int) -> bool:
    if not process_exists(pid):
        return True

    signals = [signal.SIGTERM]
    if os.name != "nt":
        signals = [signal.SIGINT, signal.SIGTERM, signal.SIGKILL]

    for sig in signals:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return True
        if wait_for_process_exit(pid, timeout_seconds=2.0):
            return True

    return not process_exists(pid)


def wait_for_process_exit(pid: int, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not process_exists(pid):
            return True
        time.sleep(0.1)
    return False


def windows_creationflags() -> int:
    if os.name != "nt":
        return 0
    return (
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0)
    )


if __name__ == "__main__":
    raise SystemExit(main())
