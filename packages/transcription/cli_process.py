"""Allowlisted CLI process execution with bounded output, time and child environment."""

from __future__ import annotations

import os
import selectors
import signal

# Commands use validated argument arrays, never a shell.
import subprocess  # nosec B404
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Protocol, cast

DEFAULT_OUTPUT_LIMIT_BYTES = 512 * 1024
DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class CommandRequest:
    executable: Path
    arguments: tuple[str, ...]
    environment: Mapping[str, str] = field(default_factory=dict, repr=False)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    output_limit_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES
    cancelled: Callable[[], bool] = field(default=lambda: False, repr=False, compare=False)

    def validate(self) -> None:
        if not self.executable.is_absolute():
            raise ValueError("command executable must be absolute")
        if not self.arguments or any(not value or "\x00" in value for value in self.arguments):
            raise ValueError("command arguments must be nonempty and contain no null bytes")
        forbidden = {"--api-key", "-k", "--project", "--admin-api-key", "--debug"}
        if forbidden.intersection(self.arguments):
            raise ValueError("credentials, project identifiers, and debug output are forbidden")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 120:
            raise ValueError("command timeout is outside the local safety boundary")
        if self.output_limit_bytes <= 0 or self.output_limit_bytes > 1024 * 1024:
            raise ValueError("command output cap is outside the local safety boundary")


@dataclass(frozen=True)
class CommandResult:
    return_code: int
    stdout: bytes = field(repr=False)
    stderr: bytes = field(repr=False)


class CommandRunError(RuntimeError):
    """Content-free child-process failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CommandRunner(Protocol):
    executes_process: bool

    def run(self, request: CommandRequest) -> CommandResult: ...


class ProcessCommandRunner:
    """Execute one allowlisted program without a shell and with bounded output."""

    executes_process = True
    _base_environment: ClassVar[dict[str, str]] = {
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "NO_COLOR": "1",
    }
    _default_allowed_environment = frozenset(
        {
            "OPENAI_API_KEY",
            "OPENAI_PROJECT_ID",
        }
    )

    def __init__(
        self,
        *,
        allowed_executables: frozenset[Path],
        extra_allowed_environment: frozenset[str] = frozenset(),
    ) -> None:
        self.allowed_executables = frozenset(
            item.resolve(strict=False) for item in allowed_executables
        )
        self.allowed_environment = self._default_allowed_environment | extra_allowed_environment

    def run(self, request: CommandRequest) -> CommandResult:
        request.validate()
        executable = request.executable.resolve(strict=False)
        if executable not in self.allowed_executables:
            raise CommandRunError("executable_not_allowlisted")
        unexpected_environment = set(request.environment) - self.allowed_environment
        if unexpected_environment:
            raise CommandRunError("child_environment_not_allowlisted")
        child_environment = dict(self._base_environment)
        child_environment.update(request.environment)
        try:
            process = subprocess.Popen(  # noqa: S603  # nosec B603
                [str(executable), *request.arguments],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd="/tmp",  # noqa: S108  # nosec B108
                env=child_environment,
                shell=False,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise CommandRunError("executable_missing") from exc
        except OSError as exc:
            raise CommandRunError("process_start_failed") from exc

        stdout = bytearray()
        stderr = bytearray()
        selector = selectors.DefaultSelector()
        assert process.stdout is not None
        assert process.stderr is not None
        for stream, destination in ((process.stdout, stdout), (process.stderr, stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, destination)
        started = time.monotonic()
        try:
            while selector.get_map():
                if request.cancelled():
                    self._terminate(process)
                    raise CommandRunError("cancelled")
                if time.monotonic() - started > request.timeout_seconds:
                    self._terminate(process)
                    raise CommandRunError("timeout")
                for key, _ in selector.select(timeout=0.05):
                    chunk = os.read(cast(Any, key.fileobj).fileno(), 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    cast(bytearray, key.data).extend(chunk)
                    if len(stdout) + len(stderr) > request.output_limit_bytes:
                        self._terminate(process)
                        raise CommandRunError("output_oversized")
            remaining = request.timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                self._terminate(process)
                raise CommandRunError("timeout")
            try:
                return_code = process.wait(timeout=remaining)
            except subprocess.TimeoutExpired as exc:
                self._terminate(process)
                raise CommandRunError("timeout") from exc
        finally:
            selector.close()
            process.stdout.close()
            process.stderr.close()
            if process.poll() is None:
                self._terminate(process)
        return CommandResult(return_code=return_code, stdout=bytes(stdout), stderr=bytes(stderr))

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=0.5)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        process.wait(timeout=1)
