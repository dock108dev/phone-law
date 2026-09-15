"""One TLS tunnel to the fixed API origin; no HTTP transcription implementation."""

from __future__ import annotations

import contextlib
import select
import socket
import socketserver
import threading
import time
from collections.abc import Iterator


class Tunnel(socketserver.TCPServer):
    """Opaque relay: CLI owns TLS verification, request serialization and response parsing."""

    allow_reuse_address = False

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), Handler)
        self.used = False
        self.stopping = threading.Event()
        self.accepted = 0
        self.denied = 0

    def handle_error(
        self, request: socket.socket | tuple[bytes, socket.socket], client_address: object
    ) -> None:
        # No request headers, credentials, paths or exception text in diagnostics.
        pass


class Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server = self.server
        assert isinstance(server, Tunnel)
        self.request.settimeout(2)
        header = bytearray()
        while not header.endswith(b"\r\n\r\n") and len(header) < 8192:
            part = self.request.recv(1)
            if not part:
                return
            header.extend(part)
        if (
            header.split(b"\r\n", 1)[0] != b"CONNECT api.openai.com:443 HTTP/1.1"
            or not header.endswith(b"\r\n\r\n")
            or server.used
        ):
            server.denied += 1
            self.request.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            return
        server.used = True  # No reconnect/retry even when connect fails.
        with socket.create_connection(("api.openai.com", 443), timeout=5) as upstream:
            server.accepted += 1
            self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            sockets = (self.request, upstream)
            for stream in sockets:
                stream.settimeout(1)
            deadline = time.monotonic() + 120
            while not server.stopping.is_set() and time.monotonic() < deadline:
                ready, _, _ = select.select(sockets, (), (), 0.1)
                for stream in ready:
                    data = stream.recv(16384)
                    if not data:
                        return
                    other = upstream if stream is self.request else self.request
                    other.sendall(data)


@contextlib.contextmanager
def fixed_tunnel() -> Iterator[Tunnel]:
    with Tunnel() as server:
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
        worker.start()
        try:
            yield server
        finally:
            server.stopping.set()
            server.shutdown()
            worker.join(timeout=8)
            if worker.is_alive():
                raise OSError("tunnel_cleanup_failed")
