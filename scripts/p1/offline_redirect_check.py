"""Pinned CLI redirect observations; dummy credential, generated silence, Seatbelt denial."""

import http.server
import io
import json
import threading
import wave

from .cli_adapter import AdapterError, Request
from .cli_process import _execute, verified_executable


def main() -> int:
    executable = verified_executable()
    media = io.BytesIO()
    with wave.open(media, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 16000)
    requests: list[dict[str, object]] = []
    code, destination = 302, "/redirected"

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

        def handle_request(self) -> None:
            size = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(size)
            requests.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "bytes": size,
                    "dummy_auth_forwarded": self.headers.get("Authorization") == "Bearer p1c-dummy",
                }
            )
            self.send_response(code if self.path == "/v1/audio/transcriptions" else 200)
            if self.path == "/v1/audio/transcriptions":
                self.send_header("Location", destination)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        do_POST = handle_request  # noqa: N815
        do_GET = handle_request  # noqa: N815

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    checks = []
    try:
        for code in (301, 302, 303, 307, 308):
            for destination in ("/redirected", "http://127.0.0.1:1/blocked"):
                requests.clear()
                outcome = "returned"
                try:
                    _execute(
                        executable,
                        Request(media.getvalue(), 1, "en"),
                        "p1c-dummy",
                        endpoint=f"http://127.0.0.1:{server.server_port}/v1",
                        timeout=5,
                    )
                except AdapterError as exc:
                    outcome = exc.code
                assert requests and requests[0]["path"] == "/v1/audio/transcriptions"
                if destination.startswith("http"):
                    assert len(requests) == 1
                checks.append(
                    {
                        "status": code,
                        "destination": destination,
                        "requests": list(requests),
                        "outcome": outcome,
                    }
                )
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
    print(
        json.dumps(
            {
                "kind": "real_pinned_cli_capture",
                "checks": checks,
                "provider_requests": 0,
                "boundary": "Seatbelt: initial loopback port only; live transport unqualified",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
