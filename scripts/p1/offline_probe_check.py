"""Pinned CLI rejects untrusted TLS through the fixed tunnel; no provider connection."""

from __future__ import annotations

import io
import json
import socket
import ssl
import subprocess  # nosec B404 - local test certificate
import tempfile
import threading
import wave
from pathlib import Path
from unittest.mock import patch

from .cli_adapter import AdapterError, Request
from .cli_process import _execute, verified_executable
from .probe_transport import fixed_tunnel


def main() -> int:
    executable = verified_executable()
    media = io.BytesIO()
    with wave.open(media, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 16000 * 11)
    threads = []
    application_bytes = []
    with tempfile.TemporaryDirectory(prefix="colacci-probe-tls-") as directory:
        root = Path(directory)
        cert, key = root / "cert.pem", root / "key.pem"
        subprocess.run(  # noqa: S603  # nosec B603 - fixed local certificate fixture
            [
                "/usr/bin/openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=api.openai.com",
                "-keyout",
                str(key),
                "-out",
                str(cert),
            ],
            check=True,
            capture_output=True,
            timeout=10,
        )
        key.chmod(0o600)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)

        def local_upstream(address: object, timeout: object = None) -> socket.socket:
            assert address == ("api.openai.com", 443)
            client, server = socket.socketpair()

            def serve() -> None:
                try:
                    with context.wrap_socket(server, server_side=True) as tls:
                        tls.settimeout(3)
                        application_bytes.append(tls.recv(4096))
                except OSError:
                    pass

            worker = threading.Thread(target=serve)
            threads.append(worker)
            worker.start()
            return client

        outcome = "returned"
        with patch("scripts.p1.probe_transport.socket.create_connection", local_upstream):
            with fixed_tunnel() as tunnel:
                try:
                    _execute(
                        executable,
                        Request(media.getvalue(), 11, "en"),
                        "probe-dummy",
                        endpoint="https://api.openai.com/v1",
                        _probe_port=tunnel.server_address[1],
                        _project="proj_offline",
                        timeout=8,
                    )
                except AdapterError as exc:
                    outcome = exc.code
            for worker in threads:
                worker.join(timeout=4)
                assert not worker.is_alive()
        assert tunnel.accepted == 1 and not application_bytes and outcome == "process_failed"
    print(
        json.dumps(
            {
                "provider_requests": 0,
                "kind": "real_pinned_cli_untrusted_TLS_rejected",
                "accepted_tunnels": tunnel.accepted,
                "application_bytes": 0,
                "outcome": outcome,
                "temporary_cert_and_media_removed": not root.exists(),
                "positive_serialization": "reuse P1B and offline_serialization_check",
                "positive_provider_TLS": "pending authorized single probe",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
