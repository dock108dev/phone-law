"""Actual pinned Mac CLI against loopback; external networking is denied by Seatbelt."""

from __future__ import annotations

import email.parser
import email.policy
import http.server
import io
import json
import socket
import subprocess  # nosec B404
import sys
import threading
import wave

from .cli_adapter import AdapterError, Request
from .cli_process import _execute, verified_executable


def main() -> int:
    executable = verified_executable()
    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\0\0" * 8000 * 31)
    media = audio.getvalue()
    captured: list[dict[str, bytes]] = []
    status = 200
    response = b'{"text":"Hola","segments":[{"start":0,"end":1,"speaker":"A","text":"Hola"}]}'

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

        def do_POST(self) -> None:
            assert self.path == "/v1/audio/transcriptions"
            assert self.headers["Authorization"] == "Bearer p1b-dummy"
            length = int(self.headers["Content-Length"])
            assert 0 < length < 1024 * 1024
            body = self.rfile.read(length)
            message = email.parser.BytesParser(policy=email.policy.default).parsebytes(
                b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + body
            )
            fields: dict[str, bytes] = {}
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                assert isinstance(name, str) and name not in fields
                value = part.get_payload(decode=True)
                assert isinstance(value, bytes)
                fields[name] = value
            captured.append(fields)
            if status == 0:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    profile = (
        "(version 1)(allow default)(deny network*)"
        f'(allow network-outbound (remote ip "localhost:{server.server_port}"))'
    )
    denial = subprocess.run(  # noqa: S603  # nosec B603
        [
            "/usr/bin/sandbox-exec",
            "-p",
            profile,
            sys.executable,
            "-c",
            "import socket; s=socket.socket(); s.settimeout(.1); "
            "\ntry: s.connect(('192.0.2.1',443))"
            "\nexcept OSError as e: assert e.errno in (1,13)"
            "\nelse: raise AssertionError('external_network_not_denied')",
        ],
        capture_output=True,
        timeout=2,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
    )
    assert denial.returncode == 0, "sandbox_denial_not_established"
    checks = []
    try:
        for code in (200, 408, 409, 429, 500, 0):
            status = code
            before = len(captured)
            try:
                result = _execute(
                    executable,
                    Request(media, 31, "es"),
                    "p1b-dummy",
                    endpoint=f"http://127.0.0.1:{server.server_port}/v1",
                    timeout=10,
                )
                assert code == 200 and json.loads(result) == json.loads(response)
            except AdapterError as exc:
                assert code != 200 and exc.code == "process_failed"
            assert len(captured) == before + 1
            assert captured[-1] == {
                "file": media,
                "language": b"es",
                "model": b"gpt-4o-transcribe-diarize",
                "response_format": b"diarized_json",
                "chunking_strategy": b"auto",
            }
            checks.append({"response_status": code, "physical_loopback_requests": 1})
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
    print(
        json.dumps(
            {
                "status": "pass",
                "binary": "1.15.0-pinned",
                "multipart": "exact_fields_and_generated_wav_bytes",
                "language": "scalar_stdin",
                "chunking": "scalar_auto",
                "output": "json_object",
                "checks": checks,
                "external_network_denial": "verified_EPERM",
                "provider_requests": 0,
                "live_verified": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
