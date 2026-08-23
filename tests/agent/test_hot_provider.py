"""Adding a provider without ending what is already running.

Configuring one used to mean restarting the runtime, which ends whatever run
is in flight -- and reaching for another provider is something a person does
*during* a task, not before one. Against the real daemon, because the property
is that a registration made now is dispatchable now.
"""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler

from loopforge.agent.kura_client import KuraAgentError
from tests.support.httpstub import QuietHTTPServer
from tests.support.kura_daemon import KuraDaemon, requires_kura


class UpstreamStub:
    """An OpenAI-compatible endpoint that records what it was sent."""

    def __init__(self, reply: str) -> None:
        self.seen: list[str] = []
        self.lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_: object) -> None:
                return

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                with outer.lock:
                    outer.seen.append(self.headers.get("Authorization", ""))
                body = (
                    f'data: {{"choices":[{{"delta":{{"content":"{reply}"}}}}]}}\n\n'
                    "data: [DONE]\n\n"
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = QuietHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        ).start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}/v1"

    def authorizations(self) -> list[str]:
        with self.lock:
            return list(self.seen)

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@requires_kura
class HotProviderRegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.daemon = KuraDaemon().start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.daemon.stop()

    def register(self, provider_id: str, upstream: UpstreamStub, token: str) -> None:
        self.daemon.client().put(
            f"/v1/providers/{provider_id}/account",
            {
                "title": provider_id,
                "protocol": "openai_compatible",
                "baseURL": upstream.base_url,
                "model": "a-model",
                "accessToken": token,
            },
        )

    def test_a_provider_added_now_can_be_dispatched_at_now(self) -> None:
        upstream = UpstreamStub("hello")
        self.addCleanup(upstream.close)

        self.register("added-live", upstream, "live-token")
        reply = self.daemon.client(timeout=20.0).post(
            "/v1/chat/query", {"query": "hi", "provider": "added-live"}
        )

        # No restart happened between the two calls; the daemon this test
        # started is the one that answered.
        self.assertIn("hello", json.dumps(reply))
        self.assertEqual(upstream.authorizations(), ["Bearer live-token"])

    def test_it_appears_in_the_inventory_without_a_restart(self) -> None:
        upstream = UpstreamStub("ok")
        self.addCleanup(upstream.close)

        self.register("added-listed", upstream, "t")
        listed = self.daemon.client().get("/v1/providers")

        ids = [item["providerId"] for item in listed.get("items", [])]
        self.assertIn("added-listed", ids)

    def test_replacing_one_takes_effect_on_the_next_request(self) -> None:
        """Editing an endpoint is the same act as adding one, and a user who
        corrects a mistake should not have to restart to see it."""
        first = UpstreamStub("first")
        second = UpstreamStub("second")
        self.addCleanup(first.close)
        self.addCleanup(second.close)

        self.register("added-replaced", first, "t")
        self.daemon.client(timeout=20.0).post(
            "/v1/chat/query", {"query": "hi", "provider": "added-replaced"}
        )
        self.register("added-replaced", second, "t")
        reply = self.daemon.client(timeout=20.0).post(
            "/v1/chat/query", {"query": "hi", "provider": "added-replaced"}
        )

        self.assertIn("second", json.dumps(reply))

    def test_removing_one_takes_it_out_of_the_inventory(self) -> None:
        upstream = UpstreamStub("ok")
        self.addCleanup(upstream.close)
        self.register("added-removed", upstream, "t")

        self.daemon.client().delete("/v1/providers/added-removed/account")
        listed = self.daemon.client().get("/v1/providers")

        ids = [item["providerId"] for item in listed.get("items", [])]
        self.assertNotIn("added-removed", ids)

    def test_a_registration_without_an_endpoint_is_refused(self) -> None:
        with self.assertRaises(KuraAgentError):
            self.daemon.client().put(
                "/v1/providers/added-empty/account",
                {"protocol": "openai_compatible", "baseURL": "", "model": "m"},
            )


if __name__ == "__main__":
    unittest.main()
