"""Offline inspection of the pinned host CLI; never invokes an API action."""

import argparse
import contextlib
import hashlib
import json
import os
import selectors
import signal
import stat
import subprocess  # nosec B404 - bounded version/help inspection only
import tempfile
import time
from pathlib import Path
from typing import Any

MAX_OUTPUT = 64 * 1024
TIMEOUT = 10.0
PROBES = {
    "version": ("--version",),
    "root": ("--help",),
    "transcription": ("audio:transcriptions", "create", "--help"),
}


class SetupError(Exception):
    """Contains only a fixed diagnostic code, never child output or environment."""


def load_contract() -> dict[str, Any]:
    return dict(json.loads(Path(__file__).with_name("cli-contract.json").read_text()))


def _probe(executable: Path, args: tuple[str, ...]) -> bytes:
    # No inherited credentials, config home, proxy, pager, stdin, or open descriptors.
    with tempfile.TemporaryDirectory(prefix="colacci-p1a-help-") as home_dir:
        private_home = str(Path(home_dir).resolve())
        try:
            process = subprocess.Popen(  # noqa: S603  # nosec B603 - approved hash, help only
                [str(executable), *args],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=private_home,
                env={"HOME": private_home, "PATH": "/usr/bin:/bin", "LC_ALL": "C"},
                start_new_session=True,
                close_fds=True,
            )
        except OSError:
            raise SetupError("executable_start_failed") from None
        output = bytearray()
        total = 0
        deadline = time.monotonic() + TIMEOUT
        assert process.stdout is not None and process.stderr is not None
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, True)
                selector.register(process.stderr, selectors.EVENT_READ, False)
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise SetupError("help_timeout")
                    for key, _ in selector.select(min(remaining, 0.1)):
                        chunk = os.read(key.fd, 8192)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        total += len(chunk)
                        if total > MAX_OUTPUT:
                            raise SetupError("help_output_limit")
                        if key.data:
                            output.extend(chunk)
                try:
                    code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    raise SetupError("help_timeout") from None
                if code:
                    raise SetupError("help_command_failed")
        finally:
            # Also remove descendants holding pipes after the direct child exits.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
            process.stdout.close()
            process.stderr.close()
        return bytes(output)


def validate_help(outputs: dict[str, bytes], contract: dict[str, Any]) -> None:
    if outputs["version"].strip() != f"openai version {contract['version']}".encode():
        raise SetupError("version_mismatch")
    required = {
        "root": ("audio:transcriptions", "--format", "json", "--base-url"),
        "transcription": (
            "--file",
            "--model",
            "gpt-4o-transcribe-diarize",
            "--response-format",
            "diarized_json",
            "--language",
            "--chunking-strategy",
            "auto",
            "30 seconds",
            "input language",
        ),
    }
    for name, tokens in required.items():
        text = outputs[name].decode("utf-8", errors="replace")
        if any(token not in text for token in tokens):
            raise SetupError("capability_mismatch")
    # This also binds source-established auth/retry behavior to the reviewed release.
    for name, data in outputs.items():
        if hashlib.sha256(data).hexdigest() != contract["help_sha256"][name]:
            raise SetupError("help_contract_changed")


def check(executable: Path | None = None) -> dict[str, Any]:
    contract = load_contract()
    selected = executable or Path.home() / contract["relative_install_path"]
    if not selected.is_absolute():
        raise SetupError("absolute_executable_required")
    try:
        resolved = selected.resolve(strict=True)
        info = resolved.stat()
        if not stat.S_ISREG(info.st_mode) or not os.access(resolved, os.X_OK):
            raise SetupError("executable_not_regular_or_executable")
        if info.st_size > 64 * 1024 * 1024:
            raise SetupError("unapproved_executable")
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    except OSError:
        raise SetupError("executable_missing_or_unreadable") from None
    if digest == contract["legacy_sha256"]:
        raise SetupError("legacy_python_cli_incompatible")
    if digest != contract["binary_sha256"]:
        raise SetupError("unapproved_executable")
    outputs = {name: _probe(resolved, args) for name, args in PROBES.items()}
    validate_help(outputs, contract)
    return {
        "status": "cli_installed_capability_checked",
        "contract": contract["contract"],
        "version": contract["version"],
        "executable": str(resolved),
        "sha256": digest,
        "help_sha256": contract["help_sha256"],
        "provider_requests": 0,
        "credentials_required": False,
        "adapter": "p1b_offline_live_blocked",
        "live_provider_verification": "pending_P1F",
        "source_contract": "docs/runbooks/p1-cli-setup.md",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path)
    args = parser.parse_args()
    try:
        result = check(args.executable)
    except SetupError as exc:
        print(json.dumps({"status": "setup_error", "code": str(exc), "provider_requests": 0}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
