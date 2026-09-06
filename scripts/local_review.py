"""Dedicated synthetic review stack and loopback-only Docker stdio relay.

No gateway network is added: the relay can reach only web's own listening port.
The Docker control process runs on the host, never inside the product containers.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import socket
import socketserver
import subprocess  # nosec B404 -- fixed local Docker and Python commands
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path("/tmp/colacci-law-slice7c-runtime")  # noqa: S108  # nosec B108 -- private owner-checked synthetic runtime
PROJECT = "colacci-law-slice7c"
PORT = 15176
DOCKER = shutil.which("docker") or "docker"
STOP = RUNTIME / "relay.stop"
READY = RUNTIME / "relay.ready"
BRIDGE = (
    "const s=require('node:net').connect(5173,'127.0.0.1');"
    "process.stdin.pipe(s);s.pipe(process.stdout);"
    "s.on('error',()=>process.exit(1));s.on('close',()=>process.exit(0));"
)


def compose(*args: str) -> None:
    environment = os.environ.copy()
    environment.update(
        COMPOSE_PROJECT_NAME=PROJECT,
        SLICE4_RUNTIME_ROOT=str(RUNTIME),
        VITE_API_BASE_URL="",
    )
    subprocess.run(  # noqa: S603  # nosec B603 -- fixed Docker command and enumerated actions
        [
            DOCKER,
            "compose",
            "-p",
            PROJECT,
            "-f",
            str(ROOT / "docker-compose.yml"),
            "-f",
            str(ROOT / "infrastructure/local/slice7c-compose.yml"),
            *args,
        ],
        cwd=ROOT,
        env=environment,
        check=True,
    )


class Relay(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        with subprocess.Popen(  # noqa: S603  # nosec B603 -- fixed command, no shell or browser input
            [DOCKER, "exec", "-i", f"{PROJECT}-web-1", "node", "-e", BRIDGE],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        ) as process:
            assert process.stdin is not None and process.stdout is not None
            incoming = process.stdin
            outgoing = process.stdout

            def upload() -> None:
                try:
                    while data := self.request.recv(65536):
                        incoming.write(data)
                        incoming.flush()
                except OSError:
                    pass
                finally:
                    with contextlib.suppress(OSError):
                        incoming.close()

            threading.Thread(target=upload, daemon=True).start()
            try:
                while data := os.read(outgoing.fileno(), 65536):
                    self.request.sendall(data)
            except OSError:
                pass
            finally:
                with contextlib.suppress(OSError):
                    self.request.shutdown(socket.SHUT_RDWR)
                process.terminate()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def relay() -> None:
    with Server(("127.0.0.1", PORT), Relay) as server:
        server.timeout = 0.5
        READY.write_text(str(os.getpid()))
        try:
            while not STOP.exists():
                server.handle_request()
        finally:
            READY.unlink(missing_ok=True)


def stop_relay() -> None:
    if READY.exists():
        STOP.touch()
        for _ in range(40):
            if not READY.exists():
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("Relay did not stop; preserve resources and inspect relay.log")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "seed", "restart", "stop", "clean", "relay"])
    action = parser.parse_args().action
    os.umask(0o077)
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    if (
        RUNTIME.is_symlink()
        or RUNTIME.stat().st_uid != os.getuid()
        or RUNTIME.stat().st_mode & 0o077
    ):
        raise RuntimeError("Runtime must be an owner-controlled private directory")
    if action == "relay":
        relay()
    elif action in {"stop", "clean"}:
        stop_relay()
        compose("down", *(["-v"] if action == "clean" else []), "--remove-orphans")
    elif action == "seed":
        compose(
            "run",
            "--rm",
            "api",
            "python",
            "scripts/seed_demo_month.py",
            "--manifest",
            "fixtures/demo-month/manifest-v2.json",
        )
    elif action == "restart":
        compose("restart", "db", "api", "worker", "web")
        compose("up", "-d", "--wait", "api", "worker", "web")
    else:
        if READY.exists():
            raise RuntimeError("Relay already running; use restart or stop first")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", PORT))
        compose("build", "api", "worker", "web", "e2e")
        compose("up", "-d", "--wait", "db")
        compose("run", "--rm", "api", "alembic", "upgrade", "head")
        compose("up", "-d", "--wait", "api", "worker", "web")
        STOP.unlink(missing_ok=True)
        with (RUNTIME / "relay.log").open("ab") as log:
            subprocess.Popen(  # noqa: S603  # nosec B603 -- fixed command, no shell or browser input
                [sys.executable, str(Path(__file__).resolve()), "relay"],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        for _ in range(40):
            if READY.exists():
                print(f"Local synthetic review: http://127.0.0.1:{PORT}")
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("Relay failed to start; inspect relay.log")


if __name__ == "__main__":
    main()
