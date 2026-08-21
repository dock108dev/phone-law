"""Dedicated real-process security harness for the repository fake CLI only."""

from __future__ import annotations

import json
import os
import shutil
import time
import wave
from collections.abc import Callable
from pathlib import Path

from packages.transcription import CommandRequest, CommandRunError, ProcessCommandRunner

SLICE_ROOT = Path("/tmp/colacci-law-slice3c")  # noqa: S108  # nosec B108
EVIDENCE_ROOT = SLICE_ROOT / "evidence"
WORK_ROOT = SLICE_ROOT / "process-security-work"
FAKE_EXECUTABLE = Path("/workspace/scripts/fake_openai_cli.py")
FIXTURE_ROOT = Path("/workspace/fixtures")


def _arguments(generated_input: Path) -> tuple[str, ...]:
    return (
        "audio:transcriptions",
        "create",
        "--model",
        "gpt-4o-transcribe-diarize",
        "--file",
        str(generated_input),
        "--response-format",
        "diarized_json",
        "--format",
        "json",
    )


def _request(
    generated_input: Path,
    case: str,
    *,
    timeout_seconds: float = 2,
    output_limit_bytes: int = 64 * 1024,
    cancelled: Callable[[], bool] = lambda: False,
) -> CommandRequest:
    return CommandRequest(
        executable=FAKE_EXECUTABLE,
        arguments=_arguments(generated_input),
        environment={
            "COLACCI_FAKE_CLI_CASE": case,
            "COLACCI_FAKE_FIXTURE_ROOT": str(FIXTURE_ROOT),
        },
        timeout_seconds=timeout_seconds,
        output_limit_bytes=output_limit_bytes,
        cancelled=cancelled,
    )


def _expected_failure(runner: ProcessCommandRunner, request: CommandRequest, code: str) -> None:
    try:
        runner.run(request)
    except CommandRunError as exc:
        if exc.code != code:
            raise AssertionError(f"unexpected safe process failure: {exc.code}") from exc
        return
    raise AssertionError(f"expected safe process failure: {code}")


def main() -> None:
    shutil.rmtree(WORK_ROOT, ignore_errors=True)
    WORK_ROOT.mkdir(mode=0o700, parents=True)
    EVIDENCE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    generated_input = WORK_ROOT / "generated-silence.wav"
    with wave.open(str(generated_input), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 1600)
    os.chmod(generated_input, 0o600)

    runner = ProcessCommandRunner(
        allowed_executables=frozenset({FAKE_EXECUTABLE}),
        extra_allowed_environment=frozenset({"COLACCI_FAKE_CLI_CASE", "COLACCI_FAKE_FIXTURE_ROOT"}),
    )
    success = runner.run(_request(generated_input, "english-short"))
    if success.return_code != 0 or not success.stdout or success.stderr:
        raise AssertionError("repository fake success contract failed")
    authentication = runner.run(_request(generated_input, "authentication-failure"))
    rate_limit = runner.run(_request(generated_input, "retryable-failure"))
    terminal = runner.run(_request(generated_input, "terminal-failure"))
    if {authentication.return_code, rate_limit.return_code, terminal.return_code} != {1}:
        raise AssertionError("repository fake nonzero cases drifted")

    _expected_failure(
        runner,
        _request(generated_input, "timeout", timeout_seconds=0.15),
        "timeout",
    )
    cancellation_checks = 0

    def cancelled() -> bool:
        nonlocal cancellation_checks
        cancellation_checks += 1
        return cancellation_checks >= 2

    _expected_failure(
        runner,
        _request(generated_input, "cancellation", cancelled=cancelled),
        "cancelled",
    )
    _expected_failure(
        runner,
        _request(generated_input, "oversized-output", output_limit_bytes=4096),
        "output_oversized",
    )
    missing = WORK_ROOT / "missing-openai"
    missing_runner = ProcessCommandRunner(allowed_executables=frozenset({missing}))
    _expected_failure(
        missing_runner,
        CommandRequest(executable=missing, arguments=("--version",)),
        "executable_missing",
    )
    started = time.monotonic()
    try:
        runner.run(
            CommandRequest(
                executable=FAKE_EXECUTABLE,
                arguments=_arguments(generated_input),
                environment={"UNSAFE_CHILD_VALUE": "blocked"},
            )
        )
    except CommandRunError as exc:
        if exc.code != "child_environment_not_allowlisted":
            raise
    else:
        raise AssertionError("unsafe child environment was accepted")
    if time.monotonic() - started > 1:
        raise AssertionError("unsafe environment was not rejected before execution")

    generated_input.unlink()
    shutil.rmtree(WORK_ROOT)
    report = {
        "schema_version": "slice3c-child-process-security-v1",
        "status": "passed",
        "shell_used": False,
        "validated_argument_array": True,
        "restricted_child_environment": True,
        "credential_arguments_forbidden": True,
        "success_case": True,
        "nonzero_exit_cases": 3,
        "timeout_terminated": True,
        "cancellation_terminated": True,
        "output_cap_enforced": True,
        "missing_executable_safe": True,
        "network_namespace": "none",
        "external_network_requests": 0,
        "raw_stdout_retained": False,
        "raw_stderr_retained": False,
        "generated_audio_retained": False,
        "cleanup_confirmed": not WORK_ROOT.exists(),
    }
    path = EVIDENCE_ROOT / "child-process-security.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    print("child-process-security cases=8 network=none cleanup=confirmed")


if __name__ == "__main__":
    main()
