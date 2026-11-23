"""Run the local Django page server and Vite asset server as one job."""

import os
import signal
import subprocess
import sys
from pathlib import Path
from shutil import which
from threading import Event

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
VITE = FRONTEND / "node_modules/vite/bin/vite.js"


def stop_children(children: list[subprocess.Popen]) -> None:
    def send(child: subprocess.Popen, sig: signal.Signals) -> None:
        try:
            os.killpg(child.pid, sig)
        except ProcessLookupError:
            pass

    for child in children:
        send(child, signal.SIGTERM)
    for child in children:
        try:
            child.wait(timeout=4)
        except subprocess.TimeoutExpired:
            send(child, signal.SIGKILL)
            child.wait()


def main() -> int:
    env = os.environ.copy()
    env.setdefault("DB_PATH", str(ROOT / "expense_tracker/pilot.sqlite3"))
    env["DEBUG"] = "True"
    node = which("node")
    if not node or not VITE.is_file():
        sys.exit("Node.js and Vite are required. Run: npm ci --prefix frontend")
    django_port = env.setdefault("DJANGO_PORT", "8000")
    vite_port = env.setdefault("VITE_PORT", "5173")
    try:
        django_port, vite_port = str(int(django_port)), str(int(vite_port))
        if django_port == vite_port or any(
            not 1 <= int(port) <= 65535 for port in (django_port, vite_port)
        ):
            raise ValueError
    except ValueError:
        sys.exit(
            "Set DJANGO_PORT and VITE_PORT to different ports between 1 and 65535."
        )
    env.update(DJANGO_PORT=django_port, VITE_PORT=vite_port)

    stopping = Event()
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    children = []
    try:
        children.append(
            subprocess.Popen(
                [node, str(VITE)], cwd=FRONTEND, env=env, start_new_session=True
            )
        )
        children.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "expense_tracker/manage.py",
                    "runserver",
                    f"127.0.0.1:{django_port}",
                ],
                cwd=ROOT,
                env=env,
                start_new_session=True,
            )
        )
        print(
            f"Open http://127.0.0.1:{django_port}/expenses/  (Ctrl+C stops the local app)",
            flush=True,
        )
        while not stopping.wait(timeout=0.2):
            for child in children:
                if child.poll() is not None:
                    return child.returncode or 1
        return 0
    finally:
        stop_children(children)


if __name__ == "__main__":
    sys.exit(main())
