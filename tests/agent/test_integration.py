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

import tempfile
import unittest
from pathlib import Path

from loopforge.agent.kura_client import KuraAgentError
from loopforge.project import HYPOTHESIS_FIELDS
from loopforge_agent.sessions import SessionStore
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
        agent.sessions_store = SessionStore(Path(tempfile.mkdtemp(prefix="lf-int-")))
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
        agent.sessions_store = SessionStore(Path(tempfile.mkdtemp(prefix="lf-int-")))
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


@requires_kura
class SessionPersistenceIntegrationTests(unittest.TestCase):
    """Conversations survive because the Agent stores them, not the runtime."""

    daemon: KuraDaemon

    @classmethod
    def setUpClass(cls) -> None:
        cls.daemon = KuraDaemon().start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.daemon.stop()

    def _agent(self, root: Path):
        from loopforge_agent.application import LoopforgeAgent

        daemon = self.daemon
        agent = object.__new__(LoopforgeAgent)

        class _Runtime:
            def status(self) -> dict:
                return {"healthy": True, "base_url": daemon.base_url, "token": daemon.token}

            def sync_context(self) -> dict:
                return {"context": {"schema_version": "game-project-context-v1"}}

        agent.runtime = _Runtime()
        agent.sessions_store = SessionStore(root)
        return agent

    def test_a_query_is_recorded_and_can_be_continued(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="lf-session-"))
        agent = self._agent(root)

        first = agent.query("first question")
        session_id = first["thread_id"]
        # Kura returns no thread, so the Agent must mint and return its own or
        # the conversation cannot be continued.
        self.assertTrue(session_id)

        agent.query("second question", session_id)

        listed = agent.sessions()["sessions"]
        self.assertEqual(len(listed), 1, "continuing reuses the session")
        self.assertEqual(listed[0]["message_count"], 4)
        self.assertEqual(listed[0]["title"], "first question")

        # A fresh Agent over the same project sees the history: it is on disk,
        # not in memory.
        reopened = self._agent(root).session(session_id)
        self.assertEqual(
            [m["author"] for m in reopened["messages"]],
            ["user", "agent", "user", "agent"],
        )

    def test_a_streamed_reply_is_recorded_once_complete(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="lf-session-"))
        agent = self._agent(root)

        events = list(agent.query_stream("stream this"))
        kinds = [name for name, _ in events]
        self.assertEqual(kinds[0], "loopforge.session", "the session id leads the stream")

        listed = agent.sessions()["sessions"]
        self.assertEqual(len(listed), 1)
        record = agent.session(listed[0]["id"])
        authors = [m["author"] for m in record["messages"]]
        self.assertEqual(authors, ["user", "agent"])
        self.assertTrue(record["messages"][1]["text"], "the streamed reply was accumulated")


@requires_kura
class HypothesisDraftIntegrationTests(unittest.TestCase):
    """Drafting runs a real model round trip and records nothing."""

    daemon: KuraDaemon

    @classmethod
    def setUpClass(cls) -> None:
        cls.daemon = KuraDaemon().start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.daemon.stop()

    def _agent(self):
        from loopforge.project import LoopforgeProject
        from loopforge_agent.application import LoopforgeAgent

        daemon = self.daemon
        root = Path(tempfile.mkdtemp(prefix="lf-draft-"))
        agent = object.__new__(LoopforgeAgent)

        class _Runtime:
            def status(self) -> dict:
                return {"healthy": True, "base_url": daemon.base_url, "token": daemon.token}

            def sync_context(self) -> dict:
                return {"context": {"schema_version": "game-project-context-v1"}}

        agent.runtime = _Runtime()
        agent.project = LoopforgeProject(root)
        agent.project.init()
        return agent

    def test_a_draft_is_returned_without_being_recorded(self) -> None:
        """The separation the requirement rests on: a proposal the user has
        not read must not already be in the project."""
        agent = self._agent()

        draft = agent.draft_hypothesis("a game about charging an attack near hazards")

        self.assertTrue(draft["draft"])
        self.assertFalse(draft["present"])
        self.assertEqual(set(draft["fields"]), set(HYPOTHESIS_FIELDS))
        # Nothing reached the project: the active experiment still has none.
        self.assertFalse(agent.hypothesis()["present"])

    def test_an_unusable_reply_still_yields_an_editable_form(self) -> None:
        """The built-in echo provider returns the prompt instead of an answer.

        A draft that cannot be parsed into a usable hypothesis must still come
        back as a complete editable form: refusing would leave the user with no
        way forward. The guarantee is the form, not its content -- the user
        reviews and corrects whatever landed there before it is recorded.

        Note the echo case also shows the parser is positional: because the
        prompt lists the headings, echoing it back leaves text under the last
        one. That is acceptable for a draft and would be caught by the
        completeness check on submission, but it is why nothing here asserts
        the fields are empty.
        """
        draft = self._agent().draft_hypothesis("anything")
        self.assertTrue(draft["draft"])
        self.assertEqual(set(draft["fields"]), set(HYPOTHESIS_FIELDS))
        self.assertTrue(draft["missing"], "an echo cannot answer a hypothesis")

    def test_an_empty_brief_is_refused_before_the_model_is_called(self) -> None:
        from loopforge_agent.application import LoopforgeAgentError

        with self.assertRaises(LoopforgeAgentError) as caught:
            self._agent().draft_hypothesis("   ")
        self.assertEqual(caught.exception.code, "BRIEF_INVALID")


@requires_kura
class RoleRoutingIntegrationTests(unittest.TestCase):
    """Routing forwarded to a live runtime, which is the only thing that can
    accept or refuse it."""

    daemon: KuraDaemon

    @classmethod
    def setUpClass(cls) -> None:
        cls.daemon = KuraDaemon().start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.daemon.stop()

    def _agent(self):
        from loopforge_agent.application import LoopforgeAgent

        daemon = self.daemon
        agent = object.__new__(LoopforgeAgent)

        class _Runtime:
            def status(self) -> dict:
                return {"healthy": True, "base_url": daemon.base_url, "token": daemon.token}

        agent.runtime = _Runtime()
        agent.sessions_store = SessionStore(Path(tempfile.mkdtemp(prefix="lf-role-")))
        return agent

    def test_a_role_is_routed_and_cleared(self) -> None:
        agent = self._agent()

        routed = agent.route_model_role("vision", "echo")
        by_role = {item["role"]: item for item in routed["roles"]}
        self.assertEqual(by_role["vision"]["provider_id"], "echo")

        cleared = agent.clear_model_role("vision")
        after = {item["role"]: item for item in cleared["roles"]}
        self.assertFalse(after["vision"]["routed"])

    def test_routing_to_an_unknown_provider_is_refused(self) -> None:
        """The runtime refuses it, and its refusal names the provider -- more
        useful than anything the Agent could restate."""
        from loopforge_agent.application import LoopforgeAgentError

        with self.assertRaises(LoopforgeAgentError) as caught:
            self._agent().route_model_role("image", "not-a-provider")
        self.assertEqual(caught.exception.code, "ROLE_ROUTING_FAILED")
        self.assertIn("not-a-provider", str(caught.exception))


@requires_kura
class ManagedProviderAuthIntegrationTests(unittest.TestCase):
    """Signing in to a provider that borrows a CLI the user already uses.

    The daemon is the only thing that knows whether that CLI is installed and
    signed in, so these run against a real one. On a machine without the CLI
    the state is `login_required` with `cli_available` false, which is a real
    answer and the one the surface has to render honestly.
    """

    daemon: KuraDaemon

    @classmethod
    def setUpClass(cls) -> None:
        cls.daemon = KuraDaemon().start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.daemon.stop()

    def _agent(self):
        from loopforge_agent.application import LoopforgeAgent

        daemon = self.daemon
        agent = object.__new__(LoopforgeAgent)

        class _Runtime:
            def status(self) -> dict:
                return {"healthy": True, "base_url": daemon.base_url, "token": daemon.token}

        agent.runtime = _Runtime()
        return agent

    def test_an_unchecked_provider_says_so_rather_than_failing(self) -> None:
        """The runtime persists auth state only once something has checked it,
        so a provider nobody has looked at answers 404. A surface needs that as
        "not checked yet", not as an error.

        Runs against its own daemon: the shared one has had its state checked
        by the other cases here, and "nobody has looked at this yet" is only
        observable before anyone has.
        """
        from loopforge_agent.application import LoopforgeAgent
        from loopforge.project import LoopforgeProject

        daemon = KuraDaemon().start()
        try:
            agent = object.__new__(LoopforgeAgent)

            class _Runtime:
                def status(self) -> dict:
                    return {
                        "healthy": True,
                        "base_url": daemon.base_url,
                        "token": daemon.token,
                    }

            agent.runtime = _Runtime()
            state = agent.provider_auth("claude_managed")
        finally:
            daemon.stop()

        self.assertEqual(state["schema_version"], "loopforge-provider-auth-v1")
        self.assertFalse(state["checked"])
        self.assertEqual(state["status"], "unknown")

    def test_a_checked_provider_reports_its_sign_in_state(self) -> None:
        agent = self._agent()
        agent.provider_auth_action("claude_managed", "refresh")

        state = agent.provider_auth("claude_managed")

        self.assertTrue(state["checked"])
        self.assertEqual(state["auth_mode"], "local_cli_bridge")
        self.assertIn(
            state["status"],
            {"unknown", "login_required", "pending_login", "authenticated", "revoked", "error"},
        )
        # Whether the borrowed tool exists at all decides whether signing in is
        # even offerable, so it is a field rather than something to infer.
        self.assertIn("cli_available", state)

    def test_starting_a_login_hands_back_the_command_to_run(self) -> None:
        """Nothing is spawned on the user's behalf. A managed provider borrows
        an account they sign into themselves, so the honest instruction is the
        command, not a button that pretends to do it."""
        agent = self._agent()

        started = agent.provider_auth_action("claude_managed", "start")

        self.assertEqual(started["status"], "pending_login")
        self.assertTrue(started["login_command"], "the command to run is the instruction")

    def test_completing_re_checks_rather_than_asserting_success(self) -> None:
        """`complete` re-detects. On a machine where the CLI never signed in it
        must not come back authenticated."""
        agent = self._agent()
        agent.provider_auth_action("claude_managed", "start")

        completed = agent.provider_auth_action("claude_managed", "complete")

        if not completed["cli_available"]:
            self.assertNotEqual(completed["status"], "authenticated")

    def test_an_unsupported_action_is_refused_before_the_runtime(self) -> None:
        from loopforge_agent.application import LoopforgeAgentError

        with self.assertRaises(LoopforgeAgentError) as caught:
            self._agent().provider_auth_action("claude_managed", "delete")
        self.assertEqual(caught.exception.code, "PROVIDER_AUTH_ACTION_INVALID")

    def test_an_unknown_provider_is_refused_by_the_runtime(self) -> None:
        from loopforge_agent.application import LoopforgeAgentError

        with self.assertRaises(LoopforgeAgentError) as caught:
            self._agent().provider_auth("not-a-provider")
        self.assertEqual(caught.exception.code, "PROVIDER_AUTH_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
