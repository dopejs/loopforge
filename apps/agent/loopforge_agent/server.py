from __future__ import annotations

import argparse
import hmac
import json
import logging
import signal
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from loopforge.errors import LoopforgeError

from .application import LoopforgeAgent, LoopforgeAgentError

MAX_REQUEST_BYTES = 64 * 1024
LOGGER = logging.getLogger("loopforge_agent")


class AgentHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self, address: tuple[str, int], agent: LoopforgeAgent, token: str
    ) -> None:
        super().__init__(address, AgentRequestHandler)
        self.agent = agent
        self.token = token


class AgentRequestHandler(BaseHTTPRequestHandler):
    server: AgentHTTPServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "service": "loopforge-agent",
                    "schema_version": "loopforge-agent-health-v1",
                },
            )
            return
        if not self._authorized():
            return
        if self.path == "/v1/status":
            self._execute(self.server.agent.status)
            return
        if self.path == "/v1/manifest":
            self._execute(self.server.agent.manifest)
            return
        if self.path == "/v1/providers":
            self._execute(self.server.agent.providers)
            return
        if self.path == "/v1/sessions":
            self._execute(self.server.agent.sessions)
            return
        self._json(HTTPStatus.NOT_FOUND, self._error("ROUTE_NOT_FOUND", "Not found."))

    def do_POST(self) -> None:
        if not self._authorized():
            return
        try:
            body = self._body()
        except LoopforgeAgentError as exc:
            self._json(HTTPStatus.BAD_REQUEST, self._error(exc.code, str(exc)))
            return
        if self.path == "/v1/start":
            self._execute(self.server.agent.start)
        elif self.path == "/v1/stop":
            self._execute(self.server.agent.stop)
        elif self.path == "/v1/query":
            self._execute(
                lambda: self.server.agent.query(
                    str(body.get("query", "")),
                    str(body["thread_id"]) if body.get("thread_id") else None,
                )
            )
        elif self.path == "/v1/query/stream":
            self._stream(
                lambda: self.server.agent.query_stream(
                    str(body.get("query", "")),
                    str(body["thread_id"]) if body.get("thread_id") else None,
                )
            )
        elif self.path == "/v1/shutdown":
            self._execute(self.server.agent.stop)
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self._json(
                HTTPStatus.NOT_FOUND, self._error("ROUTE_NOT_FOUND", "Not found.")
            )

    def _authorized(self) -> bool:
        expected = f"Bearer {self.server.token}"
        supplied = self.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied, expected):
            self._json(
                HTTPStatus.UNAUTHORIZED,
                self._error("AUTHORIZATION_REQUIRED", "Authorization required."),
            )
            return False
        return True

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise LoopforgeAgentError(
                "Content-Length is invalid.", "REQUEST_INVALID"
            ) from exc
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise LoopforgeAgentError("Request is too large.", "REQUEST_TOO_LARGE")
        if length == 0:
            return {}
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LoopforgeAgentError(
                "Request JSON is invalid.", "REQUEST_INVALID"
            ) from exc
        if not isinstance(value, dict):
            raise LoopforgeAgentError(
                "Request JSON must be an object.", "REQUEST_INVALID"
            )
        return value

    def _execute(self, operation: Any) -> None:
        try:
            self._json(HTTPStatus.OK, operation())
        except LoopforgeAgentError as exc:
            status = (
                HTTPStatus.CONFLICT
                if exc.code == "AGENT_NOT_READY"
                else HTTPStatus.BAD_REQUEST
            )
            self._json(status, self._error(exc.code, str(exc)))
        except LoopforgeError as exc:
            self._json(
                HTTPStatus.BAD_REQUEST,
                self._error(exc.diagnostic_code, exc.message, exc.details),
            )
        except Exception:
            LOGGER.exception("Unhandled Loopforge Agent request failure")
            self._json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                self._error("INTERNAL_ERROR", "The agent request failed."),
            )

    def _stream(self, operation: Any) -> None:
        """Relay a generator of `(event, data)` pairs as Server-Sent Events.

        Failures raised before the first event become a normal JSON error
        response. Once the stream has started the status line is already sent,
        so a later failure is reported as a terminal `error` event instead --
        the client has to learn the run failed, and cannot learn it from a
        status code any more.
        """
        try:
            events = operation()
        except LoopforgeAgentError as exc:
            status = (
                HTTPStatus.CONFLICT
                if exc.code == "AGENT_NOT_READY"
                else HTTPStatus.BAD_REQUEST
            )
            self._json(status, self._error(exc.code, str(exc)))
            return
        except LoopforgeError as exc:
            self._json(
                HTTPStatus.BAD_REQUEST,
                self._error(exc.diagnostic_code, exc.message, exc.details),
            )
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            for event, data in events:
                self._sse(event, data)
        except (LoopforgeError, OSError) as exc:
            LOGGER.warning("Loopforge Agent stream failed: %s", exc)
            self._sse("error", json.dumps({"message": str(exc)}, ensure_ascii=True))
        except Exception:
            LOGGER.exception("Unhandled Loopforge Agent stream failure")
            self._sse(
                "error", json.dumps({"message": "the agent stream failed"}, ensure_ascii=True)
            )

    def _sse(self, event: str, data: str) -> None:
        # Each data line is emitted separately: an embedded newline would
        # otherwise terminate the event early and truncate the payload.
        chunk = f"event: {event}\n"
        for line in data.split("\n"):
            chunk += f"data: {line}\n"
        self.wfile.write((chunk + "\n").encode("utf-8"))
        self.wfile.flush()

    @staticmethod
    def _error(code: str, message: str, details: Any = None) -> dict[str, Any]:
        return {
            "schema_version": "loopforge-agent-error-v1",
            "error": {"code": code, "message": message, "details": details or {}},
        }

    def _json(self, status: HTTPStatus, value: dict[str, Any]) -> None:
        payload = json.dumps(value, ensure_ascii=True, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loopforge-agent")
    subcommands = parser.add_subparsers(dest="command", required=True)
    serve = subcommands.add_parser("serve", help="Run the local Loopforge Agent.")
    serve.add_argument("--project", required=True, type=Path)
    serve.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "::1"))
    serve.add_argument("--port", required=True, type=int)
    serve.add_argument("--token", required=True)
    serve.add_argument("--kura-binary")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command != "serve":
        return 2
    if not 0 < arguments.port < 65_536:
        raise SystemExit("--port must be between 1 and 65535")
    if len(arguments.token) < 32:
        raise SystemExit("--token must contain at least 32 characters")
    agent = LoopforgeAgent(arguments.project, arguments.kura_binary)
    server = AgentHTTPServer((arguments.host, arguments.port), agent, arguments.token)

    def request_shutdown(signum: int, frame: object) -> None:
        del signum, frame
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        try:
            agent.stop()
        except Exception:
            pass
        server.server_close()
    return 0
