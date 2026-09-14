"""Separate deterministic process harness. Run with OS-enforced network denial."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

from .cli_adapter import AdapterError, Request
from .cli_process import _execute

FAKE = """#!PYTHON
import os, sys, time, signal
from pathlib import Path
mode = Path(__file__).stem
allowed = {'HOME','TMPDIR','PATH','LC_ALL','OPENAI_API_KEY','LC_CTYPE'}
assert set(os.environ) <= allowed | {'__CF_USER_TEXT_ENCODING'}
assert os.environ['OPENAI_API_KEY'] == 'p1b-dummy'
home = Path.cwd()
assert home.stat().st_mode & 0o777 == 0o700
assert (home/'generated.wav').stat().st_mode & 0o777 == 0o600
if mode == 'early': sys.exit(7)
if mode == 'broken':
 os.close(0); time.sleep(1); sys.exit(0)
body = sys.stdin.read()
assert body == '{"language": "es"}'
if mode == 'overflow':
 pid = os.fork()
 while True: os.write(1 if pid else 2, b'x'*8192)
if mode in ('timeout','cancel','descendant'):
 pid = os.fork()
 if pid == 0:
  signal.signal(signal.SIGTERM, signal.SIG_IGN)
  while True: time.sleep(1)
 Path(__file__).with_suffix('.pid').write_text(str(pid))
 if mode == 'descendant': sys.exit(0)
 while True: time.sleep(1)
if mode == 'malformed': print('{'); sys.exit(0)
print('{}')
"""


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network-denied", action="store_true", required=True)
    parser.parse_args()
    # Require OS denial using a numeric reserved documentation address.
    probe = socket.socket()
    probe.settimeout(0.1)
    try:
        probe.connect(("192.0.2.1", 443))
    except OSError as exc:
        if exc.errno not in (1, 13, 101, 65, 51):
            raise RuntimeError("network_denial_not_established") from None
    else:
        raise RuntimeError("network_denial_not_established")
    finally:
        probe.close()
    results: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="colacci-p1b-process-proof-") as directory:
        root = Path(directory)
        created: list[Path] = []
        original = tempfile.mkdtemp

        def tracked(*args: object, **kwargs: object) -> str:
            value = original(prefix="colacci-p1b-input-", dir=root)
            created.append(Path(value))
            return value

        for mode, expected in [
            ("success", None),
            ("malformed", None),
            ("early", "process_failed"),
            ("overflow", "output_overflow"),
            ("timeout", "timeout"),
            ("cancel", "cancelled"),
            ("descendant", "timeout"),
            ("missing", "spawn_failed"),
        ]:
            executable = root / mode
            if mode != "missing":
                executable.write_text(FAKE.replace("PYTHON", sys.executable))
                executable.chmod(0o700)
            cancellation = threading.Event()
            timer = threading.Timer(0.15, cancellation.set)
            if mode == "cancel":
                timer.start()
            created.clear()
            try:
                with patch("scripts.p1.cli_process.tempfile.mkdtemp", tracked):
                    result = _execute(
                        executable,
                        Request(b"generated", 40, "es"),
                        "p1b-dummy",
                        timeout=0.5,
                        cancel=cancellation,
                    )
                assert expected is None
                assert result == (b"{\n" if mode == "malformed" else b"{}\n")
            except AdapterError as exc:
                assert exc.code == expected, (mode, exc.code)
            finally:
                timer.cancel()
                timer.join() if mode == "cancel" else None
            assert all(not p.exists() for p in created)
            pidfile = executable.with_suffix(".pid")
            if pidfile.exists():
                pid = int(pidfile.read_text())
                # Linux zombies may remain until namespace init reaps; they are terminated.
                procstat = Path(f"/proc/{pid}/stat")
                for _ in range(100):
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        break
                    if procstat.exists() and procstat.read_text().split()[2] == "Z":
                        break
                    time.sleep(0.01)
                else:
                    raise AssertionError("descendant_still_running")
            results[mode] = "pass"
        # Deterministically inject cleanup and broken-pipe OS failures in this process harness.
        executable = root / "success"
        original_remove = shutil.rmtree
        created = []
        with (
            patch("scripts.p1.cli_process.tempfile.mkdtemp", tracked),
            patch("scripts.p1.cli_process.shutil.rmtree", side_effect=OSError),
        ):
            try:
                _execute(executable, Request(b"generated", 40, "es"), "p1b-dummy", timeout=0.5)
            except AdapterError as exc:
                assert exc.code == "cleanup_failed"
            else:
                raise AssertionError
        # Remove only this harness's retained failed-cleanup input.
        for path in created:
            if path.is_dir() and (path / "generated.wav").exists():
                original_remove(path)
        with patch("scripts.p1.cli_process.os.write", side_effect=BrokenPipeError):
            try:
                _execute(executable, Request(b"generated", 40, "es"), "p1b-dummy", timeout=0.5)
            except AdapterError as exc:
                assert exc.code == "stdin_failed"
            else:
                raise AssertionError
        results["cleanup_failure_injected"] = "pass"
        results["broken_stdin_injected"] = "pass"
    print(json.dumps({"platform": sys.platform, "checks": results, "provider_requests": 0}))
    return 0


def main() -> int:
    # Test-only executable substitution; the real primitive verifies the P1A pin.
    with (
        patch("scripts.p1.cli_process.verified_executable", side_effect=lambda path: path),
        patch("scripts.p1.cli_process._network_prefix", return_value=()),
    ):
        return _main()


if __name__ == "__main__":
    raise SystemExit(main())
