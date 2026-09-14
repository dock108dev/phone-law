"""Bounded POSIX process primitive, exercised only by isolated offline harnesses in P1B.

No operator entry point calls this primitive. LiveRunner fails before it; P1C must
add durable admission before connecting the two. Test endpoint/executable injection
belongs only to the separate harness, never operator configuration.
"""

from __future__ import annotations

import contextlib
import os
import platform
import selectors
import shutil
import signal
import subprocess  # nosec B404 - bounded direct argv, private environment
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from .cli_adapter import MAX_OUTPUT, AdapterError, Request
from .cli_check import SetupError, check


def verified_executable(selected: Path | None = None) -> Path:
    try:
        return Path(check(selected)["executable"])
    except SetupError:
        raise AdapterError("tool_rejected") from None


def _network_prefix(endpoint: str) -> tuple[str, ...]:
    if platform.system() != "Darwin":
        raise AdapterError("tool_rejected")
    port = urlsplit(endpoint).port
    if port is None:
        raise AdapterError("tool_rejected")
    profile = (
        "(version 1)(allow default)(deny network*)"
        f'(allow network-outbound (remote ip "localhost:{port}"))'
    )
    return ("/usr/bin/sandbox-exec", "-p", profile)


def _execute(
    executable: Path,
    request: Request,
    credential: str,
    *,
    endpoint: str = "http://127.0.0.1:1/v1",
    timeout: float = 120,
    cancel: threading.Event | None = None,
) -> bytes:
    """Private primitive; test overrides only under enforced OS network isolation."""
    if not executable.is_absolute() or not 0 < timeout <= 120:
        raise AdapterError("tool_rejected")
    # P1B cannot address a provider even by calling this private primitive directly.
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError, TypeError:
        raise AdapterError("p1c_required") from None
    if (
        port is None
        or parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username
        or parsed.password
    ):
        raise AdapterError("p1c_required")
    if type(credential) is not str or not credential or "\0" in credential:
        raise AdapterError("invalid_input")
    if cancel is not None and cancel.is_set():
        raise AdapterError("cancelled")
    executable = verified_executable(executable)
    directory: Path | None = None
    process: subprocess.Popen[bytes] | None = None
    result = bytearray()
    failure: AdapterError | None = None
    try:
        directory = Path(tempfile.mkdtemp(prefix="colacci-p1b-")).resolve()
        directory.chmod(0o700)
        media = directory / "generated.wav"
        with media.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(request.media)
        args = [
            *_network_prefix(endpoint),
            str(executable),
            *request.arguments,
            "--file",
            str(media),
            "--base-url",
            endpoint,
        ]
        try:
            process = subprocess.Popen(  # noqa: S603  # nosec B603 - no shell, isolated runner
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=directory,
                env={
                    "HOME": str(directory),
                    "TMPDIR": str(directory),
                    "PATH": "/usr/bin:/bin",
                    "LC_ALL": "C",
                    "OPENAI_API_KEY": credential,
                },
                close_fds=True,
                start_new_session=True,
            )
        except OSError:
            raise AdapterError("spawn_failed") from None
        assert (
            process.stdin is not None and process.stdout is not None and process.stderr is not None
        )
        deadline = time.monotonic() + timeout
        total = 0
        body = memoryview(request.body)
        with selectors.DefaultSelector() as selector:
            for pipe in (process.stdin, process.stdout, process.stderr):
                os.set_blocking(pipe.fileno(), False)
            selector.register(process.stdin, selectors.EVENT_WRITE, "input")
            selector.register(process.stdout, selectors.EVENT_READ, "output")
            selector.register(process.stderr, selectors.EVENT_READ, "error")
            while selector.get_map() or process.poll() is None:
                if cancel is not None and cancel.is_set():
                    raise AdapterError("cancelled")
                if time.monotonic() >= deadline:
                    raise AdapterError("timeout")
                for key, _ in selector.select(min(0.025, max(0, deadline - time.monotonic()))):
                    if key.data == "input":
                        try:
                            written = os.write(key.fd, body)
                        except BrokenPipeError:
                            raise AdapterError("stdin_failed") from None
                        body = body[written:]
                        if not body:
                            selector.unregister(key.fileobj)
                            process.stdin.close()
                    else:
                        chunk = os.read(key.fd, 8192)
                        if not chunk:
                            selector.unregister(key.fileobj)
                        total += len(chunk)
                        if total > MAX_OUTPUT:
                            raise AdapterError("output_overflow")
                        if key.data == "output":
                            result.extend(chunk)
            if process.returncode:
                raise AdapterError("process_failed")
    except AdapterError as exc:
        failure = exc
    except OSError:
        failure = AdapterError("process_failed")
    finally:
        try:
            if process is not None:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=2)
                for cleanup_pipe in (process.stdin, process.stdout, process.stderr):
                    if cleanup_pipe is not None:
                        cleanup_pipe.close()
            if directory is not None:
                shutil.rmtree(directory)
                if directory.exists():
                    raise OSError
        except OSError, subprocess.TimeoutExpired:
            failure = AdapterError("cleanup_failed")
    if failure is not None:
        raise failure
    return bytes(result)
