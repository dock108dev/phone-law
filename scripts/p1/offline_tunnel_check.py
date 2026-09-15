"""Offline fixed-origin relay checks. No external connection function is reachable."""

import json
import socket
import threading
from unittest.mock import patch

from .probe_transport import fixed_tunnel


def main() -> int:
    upstreams = []
    peers = []

    def upstream(address: object, timeout: object = None) -> socket.socket:
        assert address == ("api.openai.com", 443)
        upstreams.append(address)
        first, second = socket.socketpair()
        peers.append(second)
        return first

    def exchange(port: int, header: bytes) -> bytes:
        with socket.socket() as client:
            client.settimeout(2)
            client.connect(("127.0.0.1", port))
            client.sendall(header)
            return client.recv(1024)

    with patch("scripts.p1.probe_transport.socket.create_connection", upstream):
        with fixed_tunnel() as tunnel:
            port = tunnel.server_address[1]
            for header in (
                b"CONNECT other.invalid:443 HTTP/1.1\r\n\r\n",
                b"CONNECT api.openai.com:80 HTTP/1.1\r\n\r\n",
                b"GET http://api.openai.com/redirect HTTP/1.1\r\n\r\n",
            ):
                assert b"403" in exchange(port, header)
            assert not upstreams
            with socket.socket() as client:
                client.settimeout(2)
                client.connect(("127.0.0.1", port))
                client.sendall(b"CONNECT api.openai.com:443 HTTP/1.1\r\n\r\n")
                assert b"200" in client.recv(1024)
                client.sendall(b"opaque-fixture-bytes")
                peers[0].settimeout(2)
                assert peers[0].recv(1024) == b"opaque-fixture-bytes"
                peers[0].sendall(b"opaque-response")
                assert client.recv(1024) == b"opaque-response"
            assert b"403" in exchange(port, b"CONNECT api.openai.com:443 HTTP/1.1\r\n\r\n")
        for peer in peers:
            peer.close()
    assert len(upstreams) == 1 and tunnel.denied == 4
    assert not any(t.name.endswith("serve_forever)") for t in threading.enumerate())
    print(
        json.dumps(
            {
                "provider_requests": 0,
                "fixed_origin_relay": "pass",
                "opaque_bidirectional_bytes": "pass",
                "cross_host_wrong_port_plain_http_and_second_tunnel": "denied",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
