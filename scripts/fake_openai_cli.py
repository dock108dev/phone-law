#!/usr/bin/env python3
"""Repository fake for the dedicated network-disabled process-security harness."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def _validated_fixture_root() -> Path:
    root = Path(os.environ["COLACCI_FAKE_FIXTURE_ROOT"]).resolve(strict=True)
    expected = Path("/workspace/fixtures").resolve(strict=True)
    if root != expected:
        raise SystemExit(64)
    return root


def _validate_arguments(arguments: list[str]) -> None:
    required = {
        "audio:transcriptions",
        "create",
        "--model",
        "gpt-4o-transcribe-diarize",
        "--file",
        "--response-format",
        "diarized_json",
        "--format",
        "json",
    }
    if not required.issubset(arguments):
        raise SystemExit(64)
    if {"--api-key", "--project", "--debug"}.intersection(arguments):
        raise SystemExit(64)


def main() -> None:
    _validate_arguments(sys.argv[1:])
    fixture_root = _validated_fixture_root()
    case = os.environ.get("COLACCI_FAKE_CLI_CASE", "")
    if case in {"english-short", "english-long", "confirmed-cleanup"}:
        sys.stdout.buffer.write(
            (fixture_root / "transcription-responses/english-diarized.json").read_bytes()
        )
        return
    if case == "spanish-short":
        sys.stdout.buffer.write(
            (fixture_root / "transcription-responses/spanish-diarized.json").read_bytes()
        )
        return
    if case == "multiple-speakers":
        sys.stdout.buffer.write(
            (fixture_root / "transcription-responses/two-unknown-speakers.json").read_bytes()
        )
        return
    if case == "text-only-fallback":
        sys.stdout.buffer.write(
            (fixture_root / "transcription-responses/text-only-fallback.json").read_bytes()
        )
        return
    if case == "malformed-json":
        sys.stdout.buffer.write(b"not-json")
        return
    if case == "unsupported-output":
        sys.stdout.buffer.write(
            (fixture_root / "cli-transcription/unsupported-output.json").read_bytes()
        )
        return
    if case in {"timeout", "cancellation"}:
        time.sleep(10)
        return
    if case == "oversized-output":
        sys.stdout.buffer.write(b"x" * (1024 * 1024))
        return
    if case == "authentication-failure":
        sys.stderr.write("authentication failure")
        raise SystemExit(1)
    if case == "retryable-failure":
        sys.stderr.write("rate limit 429")
        raise SystemExit(1)
    if case == "terminal-failure":
        sys.stderr.write("terminal provider failure")
        raise SystemExit(1)
    raise SystemExit(64)


if __name__ == "__main__":
    main()
