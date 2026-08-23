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
        if self.path.startswith("/v1/settings/provider/auth/"):
            provider_id = self.path[len("/v1/settings/provider/auth/") :]
            self._execute(lambda: self.server.agent.provider_auth(provider_id))
            return
        if self.path == "/v1/settings/operator":
            self._execute(self.server.agent.operator_settings)
            return
        if self.path == "/v1/settings/provider":
            self._execute(self.server.agent.provider_settings)
            return
        if self.path == "/v1/project/health":
            self._execute(self.server.agent.project_health)
            return
        if self.path == "/v1/project/history":
            self._execute(self.server.agent.history)
            return
        if self.path == "/v1/decision":
            self._execute(self.server.agent.decision)
            return
        if self.path == "/v1/playtest":
            self._execute(self.server.agent.playtest)
            return
        if self.path == "/v1/evidence":
            self._execute(self.server.agent.evidence)
            return
        if self.path == "/v1/hypothesis":
            self._execute(self.server.agent.hypothesis)
            return
        if self.path == "/v1/project/status":
            self._execute(self.server.agent.project_status)
            return
        if self.path == "/v1/runs":
            self._execute(self.server.agent.runs)
            return
        if self.path in ("/v1/runs?operation=test", "/v1/runs?operation=build"):
            operation = self.path.split("=", 1)[1]
            self._execute(lambda: self.server.agent.runs(operation))
            return
        if self.path.startswith("/v1/gate/"):
            # No reason or approver here: this is the read-only view of where
            # the project stands. Transitions that need those supply them on
            # the advance itself, and their absence is correctly reported as a
            # missing requirement rather than assumed.
            stage = self.path[len("/v1/gate/") :]
            self._execute(lambda: self.server.agent.gate(stage))
            return
        if self.path.startswith("/v1/runs/"):
            run_id = self.path[len("/v1/runs/") :]
            self._execute(lambda: self.server.agent.run(run_id))
            return
        if self.path.startswith("/v1/sessions/"):
            session_id = self.path[len("/v1/sessions/") :]
            self._execute(lambda: self.server.agent.session(session_id))
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
        elif self.path == "/v1/hypothesis/draft":
            self._execute(
                lambda: self.server.agent.draft_hypothesis(str(body.get("brief", "")))
            )
        elif self.path == "/v1/hypothesis":
            self._execute(
                lambda: self.server.agent.create_hypothesis(
                    body.get("fields"),
                    str(body["approver_id"]) if body.get("approver_id") else None,
                    str(body["approver_name"]) if body.get("approver_name") else None,
                    str(body["rationale"]) if body.get("rationale") else None,
                )
            )
        elif self.path == "/v1/settings/operator":
            self._execute(
                lambda: self.server.agent.save_operator_settings(str(body.get("name", "")))
            )
        elif self.path == "/v1/settings/provider":
            self._execute(
                lambda: self.server.agent.save_provider_settings(
                    str(body.get("base_url", "")),
                    str(body.get("api_key", "")),
                    str(body.get("model", "")),
                    str(body.get("display_name", "")),
                    str(body.get("protocol", "")),
                )
            )
        elif self.path == "/v1/settings/provider/probe":
            self._execute(
                lambda: self.server.agent.probe_provider(
                    str(body.get("base_url", "")), str(body.get("api_key", ""))
                )
            )
        elif self.path == "/v1/settings/provider/auth":
            self._execute(
                lambda: self.server.agent.provider_auth_action(
                    str(body.get("provider_id", "")), str(body.get("action", ""))
                )
            )
        elif self.path == "/v1/settings/role":
            self._execute(
                lambda: self.server.agent.route_model_role(
                    str(body.get("role", "")),
                    str(body.get("provider_id", "")),
                    str(body.get("model", "")),
                )
            )
        elif self.path == "/v1/settings/role/clear":
            self._execute(
                lambda: self.server.agent.clear_model_role(str(body.get("role", "")))
            )
        elif self.path == "/v1/settings/provider/forget":
            self._execute(self.server.agent.forget_provider_settings)
        elif self.path == "/v1/project/reconcile":
            self._execute(
                lambda: self.server.agent.reconcile(body.get("apply") is True)
            )
        elif self.path == "/v1/decision":
            self._execute(
                lambda: self.server.agent.decide(
                    str(body.get("decision", "")),
                    body.get("evidence_ids"),
                    str(body["approver_id"]) if body.get("approver_id") else None,
                    str(body["approver_name"]) if body.get("approver_name") else None,
                    str(body["rationale"]) if body.get("rationale") else None,
                    body.get("revised_fields"),
                )
            )
        elif self.path == "/v1/playtest/protocol/draft":
            self._execute(self.server.agent.draft_playtest_protocol)
        elif self.path == "/v1/playtest/protocol":
            self._execute(
                lambda: self.server.agent.create_playtest_protocol(
                    str(body.get("content", ""))
                )
            )
        elif self.path == "/v1/playtest/report":
            self._execute(
                lambda: self.server.agent.import_playtest_report(body.get("report"))
            )
        elif self.path == "/v1/capture":
            self._execute(
                lambda: self.server.agent.register_capture(str(body.get("path", "")))
            )
        elif self.path == "/v1/gate":
            # A POST for a read, because this check takes arguments. The early
            # decision gate tests the reason and approver it is *given*, not
            # anything recorded, so a parameterless GET would report them
            # missing while the advance that supplies them succeeds.
            self._execute(
                lambda: self.server.agent.gate(
                    str(body.get("stage", "")),
                    str(body["reason"]) if body.get("reason") else None,
                    str(body["approver_id"]) if body.get("approver_id") else None,
                    str(body["approver_name"]) if body.get("approver_name") else None,
                    str(body["rationale"]) if body.get("rationale") else None,
                )
            )
        elif self.path == "/v1/advance":
            self._execute(
                lambda: self.server.agent.advance(
                    str(body.get("stage", "")),
                    str(body["reason"]) if body.get("reason") else None,
                    str(body["approver_id"]) if body.get("approver_id") else None,
                    str(body["approver_name"]) if body.get("approver_name") else None,
                    str(body["rationale"]) if body.get("rationale") else None,
                )
            )
        elif self.path == "/v1/project/init":
            self._execute(self.server.agent.init_project)
        elif self.path == "/v1/engine/run":
            self._execute(
                lambda: self.server.agent.run_engine(str(body.get("operation", "")))
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

    @staticmethod
    def _status_for(exc: LoopforgeAgentError) -> HTTPStatus:
        """Map an agent failure to a status the caller can act on.

        A missing session or run is not a malformed request: answering 400
        sends whoever is debugging it to look at their own payload, when the
        record simply is not there.
        """
        if exc.code == "AGENT_NOT_READY":
            return HTTPStatus.CONFLICT
        if exc.code.endswith("_NOT_FOUND"):
            return HTTPStatus.NOT_FOUND
        return HTTPStatus.BAD_REQUEST

    def _execute(self, operation: Any) -> None:
        try:
            self._json(HTTPStatus.OK, operation())
        except LoopforgeAgentError as exc:
            self._json(self._status_for(exc), self._error(exc.code, str(exc)))
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
            self._json(self._status_for(exc), self._error(exc.code, str(exc)))
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
