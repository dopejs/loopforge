"""A loopback HTTP server for tests, without the half-second name lookup.

`HTTPServer.server_bind` calls `socket.getfqdn`, a reverse DNS lookup that
blocks for roughly half a second on a machine with no reverse record for the
loopback address. Every stand-in endpoint in the suite paid it, twice per test.
"""

from __future__ import annotations

import socketserver
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class QuietHTTPServer(HTTPServer):
    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)


def serve(handler: type[BaseHTTPRequestHandler]) -> tuple[QuietHTTPServer, str]:
    """Start a server on an ephemeral port. Returns it and its base URL."""
    server = QuietHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    ).start()
    return server, f"http://127.0.0.1:{server.server_port}"
