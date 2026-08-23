"""Replacing a provider's credential while the daemon runs.

Against the real daemon and a real upstream socket, because the thing being
checked is what goes out on the wire after a swap. An OAuth access token lasts
about an hour and the daemon outlives it many times over, so without this the
only options are a restart -- which drops whatever run is in flight -- or a
token that quietly goes stale and turns every later dispatch into a 401 the
user reads as a broken endpoint.
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

    def __init__(self) -> None:
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
                    b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
                    b"data: [DONE]\n\n"
                )
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
class CredentialRotationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.upstream = UpstreamStub()
        cls.daemon = KuraDaemon()
        cls.daemon._environment.update(
            {
                "KURA_LLM_DEFAULT_PROVIDER": "openai_compatible",
                "KURA_LLM_OPENAI_COMPATIBLE_BASE_URL": cls.upstream.base_url,
                "KURA_LLM_OPENAI_COMPATIBLE_API_KEY": "boot-token",
                "KURA_LLM_OPENAI_COMPATIBLE_MODEL": "test-model",
            }
        )
        cls.daemon.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.daemon.stop()
        cls.upstream.close()

    def dispatch(self) -> None:
        self.daemon.client(timeout=20.0).post("/v1/chat/query", {"query": "hello"})

    def test_a_rotated_token_reaches_the_upstream_without_a_restart(self) -> None:
        # Its own baseline rather than the value the daemon booted with: these
        # tests share one daemon, so anything that reads boot state is really
        # reading whichever test ran first.
        self.daemon.client().put(
            "/v1/providers/openai_compatible/credential", {"apiKey": "first-token"}
        )
        before = len(self.upstream.authorizations())
        self.dispatch()

        self.daemon.client().put(
            "/v1/providers/openai_compatible/credential", {"apiKey": "second-token"}
        )
        self.dispatch()

        seen = self.upstream.authorizations()[before:]
        self.assertEqual(len(seen), 2, f"both dispatches reached the upstream: {seen}")
        # Two dispatches, two different bearers, nothing restarted between them.
        self.assertEqual(seen[0], "Bearer first-token")
        self.assertEqual(seen[1], "Bearer second-token")

    def test_the_boot_credential_is_used_before_anything_replaces_it(self) -> None:
        """A daemon of its own, so this reads the value it actually booted with
        rather than whatever a sibling test last set."""
        upstream = UpstreamStub()
        self.addCleanup(upstream.close)
        daemon = KuraDaemon()
        daemon._environment.update(
            {
                "KURA_LLM_DEFAULT_PROVIDER": "openai_compatible",
                "KURA_LLM_OPENAI_COMPATIBLE_BASE_URL": upstream.base_url,
                "KURA_LLM_OPENAI_COMPATIBLE_API_KEY": "boot-token",
                "KURA_LLM_OPENAI_COMPATIBLE_MODEL": "test-model",
            }
        )
        daemon.start()
        self.addCleanup(daemon.stop)

        daemon.client(timeout=20.0).post("/v1/chat/query", {"query": "hello"})

        self.assertEqual(upstream.authorizations(), ["Bearer boot-token"])

    def test_clearing_the_credential_stops_it_being_sent(self) -> None:
        """Signing an account out has to actually stop the token going out."""
        self.daemon.client().put(
            "/v1/providers/openai_compatible/credential", {"apiKey": "temporary"}
        )
        before = len(self.upstream.authorizations())

        self.daemon.client().put(
            "/v1/providers/openai_compatible/credential", {"apiKey": ""}
        )
        self.dispatch()

        self.assertEqual(self.upstream.authorizations()[before:], [""])

    def test_a_provider_with_nothing_to_replace_is_refused(self) -> None:
        """The managed bridges borrow a CLI's own session and hold no
        credential, so accepting this would be a silent no-op that reads as
        success."""
        with self.assertRaises(KuraAgentError) as caught:
            self.daemon.client().put(
                "/v1/providers/claude_managed/credential", {"apiKey": "x"}
            )

        self.assertIn("404", str(caught.exception))

    def test_a_body_without_a_key_does_not_clear_the_credential(self) -> None:
        """An empty or malformed body read as "clear it" would disable the
        provider on a mistake nobody made deliberately."""
        self.daemon.client().put(
            "/v1/providers/openai_compatible/credential", {"apiKey": "kept-token"}
        )

        with self.assertRaises(KuraAgentError):
            self.daemon.client().put("/v1/providers/openai_compatible/credential", None)

        before = len(self.upstream.authorizations())
        self.dispatch()
        self.assertEqual(self.upstream.authorizations()[before:], ["Bearer kept-token"])

    def test_the_credential_is_never_echoed_back(self) -> None:
        response = self.daemon.client().put(
            "/v1/providers/openai_compatible/credential", {"apiKey": "secret-token"}
        )

        self.assertNotIn("secret-token", json.dumps(response))
        self.assertTrue(response.get("updated"))


if __name__ == "__main__":
    unittest.main()
