"""Integration tests against a real Kura daemon.

These cover the failures that unit tests structurally cannot: a client that
rejects a URL shape, a route that needs a bearer token, an authenticated token
that still fails tenant resolution, a response field named differently than
assumed. Every one of those shipped at some point in this stack and was found
only by talking to a live daemon.

Skipped when no Kura binary is available, so CI (which does not build the
sidecar) stays green.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from loopforge.agent.kura_client import KuraAgentError
from tests.support.kura_daemon import KuraDaemon, requires_kura


@requires_kura
class KuraClientIntegrationTests(unittest.TestCase):
    daemon: KuraDaemon

    @classmethod
    def setUpClass(cls) -> None:
        cls.daemon = KuraDaemon().start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.daemon.stop()

    def test_v1_is_closed_without_a_token(self) -> None:
        """Health is open; everything else requires pairing."""
        anonymous = self.daemon.anonymous_client()
        self.assertTrue(anonymous.get("/healthz")["ok"])
        with self.assertRaises(KuraAgentError) as caught:
            anonymous.get("/v1/model-roles")
        self.assertIn("401", str(caught.exception))

    def test_a_paired_token_resolves_and_authorizes(self) -> None:
        """Authenticating is not enough: the token must resolve to a tenant.

        A token with an empty principal authenticates and then fails resolution
        with 403, which is why this asserts a real payload rather than merely
        'no exception'.
        """
        identity = self.daemon.client().get("/v1/auth/me")
        self.assertEqual(identity["principal"]["principalKind"], "local_operator")
        self.assertEqual(identity["principal"]["status"], "active")
        self.assertTrue(identity["defaultTenant"]["tenantId"])

    def test_query_parameters_travel_outside_the_path(self) -> None:
        """The client rejects a path containing '?', so an expansion has to be
        passed as a query argument. Building it into the path silently failed
        before this was pinned."""
        client = self.daemon.client()
        with self.assertRaises(KuraAgentError):
            client.get("/v1/providers?include=models")
        expanded = client.get("/v1/providers", {"include": "models"})
        self.assertIn("models", expanded)
        self.assertNotIn("models", client.get("/v1/providers"))

    def test_model_roles_round_trip(self) -> None:
        client = self.daemon.client()
        routed = client.put("/v1/model-roles/vision", {"providerId": "echo"})
        self.assertTrue(routed["routed"])
        self.assertEqual(routed["source"], "store")

        listed = {item["role"]: item for item in client.get("/v1/model-roles")["items"]}
        self.assertEqual(listed["vision"]["providerId"], "echo")
        # Unrouted roles stay in the listing so the UI can show them.
        self.assertIn("video", listed)
        self.assertFalse(listed["video"]["routed"])

        # A 204 with no body must not be treated as malformed JSON.
        self.assertEqual(client.delete("/v1/model-roles/vision"), {})
        after = {item["role"]: item for item in client.get("/v1/model-roles")["items"]}
        self.assertFalse(after["vision"]["routed"])

    def test_routing_an_unknown_provider_is_refused(self) -> None:
        """Routing to a provider that does not exist would only fail later, at
        dispatch time, far from the change that caused it."""
        with self.assertRaises(KuraAgentError) as caught:
            self.daemon.client().put("/v1/model-roles/image", {"providerId": "nope"})
        self.assertIn("404", str(caught.exception))

    def test_streaming_yields_incremental_events(self) -> None:
        events = list(
            self.daemon.client().stream("/v1/chat/query/stream", {"query": "hi"}, timeout=60)
        )
        names = [name for name, _ in events]
        self.assertEqual(names[0], "chat.query.started")
        # The point of streaming is partial output before completion.
        self.assertGreater(names.count("chat.query.delta"), 1)
        self.assertTrue(any(name.endswith("completed") for name in names), names)


@requires_kura
class AgentProjectionIntegrationTests(unittest.TestCase):
    """The Agent's provider projection against a live runtime rather than a stub."""

    daemon: KuraDaemon

    @classmethod
    def setUpClass(cls) -> None:
        cls.daemon = KuraDaemon().start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.daemon.stop()

    def _agent(self) -> object:
        from loopforge_agent.application import LoopforgeAgent

        agent = object.__new__(LoopforgeAgent)
        daemon = self.daemon

        class _Runtime:
            def status(self) -> dict:
                return {
                    "healthy": True,
                    "base_url": daemon.base_url,
                    "token": daemon.token,
                }

        agent.runtime = _Runtime()
        return agent

    def test_projects_a_live_inventory(self) -> None:
        result = self._agent().providers()
        self.assertEqual(result["schema_version"], "loopforge-provider-v1")
        self.assertNotIn("reason", result)
        by_id = {p["id"]: p for p in result["providers"]}
        # `echo` is Kura's built-in provider and is always ready, which makes it
        # a stable anchor for this assertion.
        self.assertIn("echo", by_id)
        self.assertEqual(by_id["echo"]["health"], "ready")

    def test_projection_stays_within_the_contract(self) -> None:
        import json

        root = Path(__file__).resolve().parents[2]
        schema = json.loads(
            (root / "contracts" / "loopforge-provider-v1.schema.json").read_text()
        )
        result = self._agent().providers()
        self.assertLessEqual(set(result), set(schema["properties"]))
        provider_props = set(schema["$defs"]["provider"]["properties"])
        for provider in result["providers"]:
            self.assertLessEqual(set(provider), provider_props, provider["id"])

    def test_roles_are_projected_from_the_runtime(self) -> None:
        roles = self._agent().providers()["roles"]
        self.assertEqual(
            [r["role"] for r in roles],
            ["primary", "vision", "image", "video", "embed"],
        )


@requires_kura
class AgentStreamingIntegrationTests(unittest.TestCase):
    """The Agent's own SSE relay, driven through its HTTP server.

    Exercising the relay rather than `query_stream` directly is deliberate: the
    bugs live in the wire format -- header order, per-line data framing, when a
    failure can still become a status code -- and none of them are visible from
    the generator.
    """

    daemon: KuraDaemon

    @classmethod
    def setUpClass(cls) -> None:
        cls.daemon = KuraDaemon().start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.daemon.stop()

    def _serve_agent(self):
        """Run a real Agent HTTP server wired to the live daemon."""
        import threading

        from loopforge_agent.application import LoopforgeAgent
        from loopforge_agent.server import AgentHTTPServer

        daemon = self.daemon
        agent = object.__new__(LoopforgeAgent)

        class _Runtime:
            def status(self) -> dict:
                return {
                    "healthy": True,
                    "base_url": daemon.base_url,
                    "token": daemon.token,
                }

            def sync_context(self) -> dict:
                return {"context": {"schema_version": "game-project-context-v1"}}

        agent.runtime = _Runtime()
        server = AgentHTTPServer(("127.0.0.1", 0), agent, "t" * 40)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, f"http://127.0.0.1:{server.server_address[1]}"

    def test_agent_relays_incremental_events(self) -> None:
        from loopforge.agent.kura_client import KuraClient

        server, base_url = self._serve_agent()
        try:
            client = KuraClient(base_url, timeout=60.0, token="t" * 40)
            events = list(client.stream("/v1/query/stream", {"query": "hi"}, timeout=60))
        finally:
            server.shutdown()
            server.server_close()

        names = [name for name, _ in events]
        self.assertIn("chat.query.started", names)
        # Partial output is the entire point; a single terminal event would
        # mean the relay buffered the run.
        self.assertGreater(names.count("chat.query.delta"), 1)

    def test_an_invalid_query_fails_before_the_stream_starts(self) -> None:
        """An empty query must be a status code, not a stream that opens and
        immediately errors -- the caller has not started rendering yet."""
        from loopforge.agent.kura_client import KuraAgentError, KuraClient

        server, base_url = self._serve_agent()
        try:
            client = KuraClient(base_url, timeout=30.0, token="t" * 40)
            with self.assertRaises(KuraAgentError) as caught:
                list(client.stream("/v1/query/stream", {"query": "   "}, timeout=30))
        finally:
            server.shutdown()
            server.server_close()
        self.assertIn("400", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
