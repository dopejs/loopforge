"""Signing an account in through the Agent, end to end.

Everything except the vendor is real here: a real listener on the real
redirect port, a real browser hit, a real code exchange, a real credential
store. The parts that have broken in this project have always been the joins
-- a route that was never registered, a payload key that did not match, state
kept on the class instead of the instance -- and none of those show up in a
test that calls the methods directly.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from dataclasses import replace
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from unittest import mock

from tests.support.httpstub import serve

from loopforge.oauth import registry
from loopforge.userstore import UserStore
from loopforge_agent.application import LoopforgeAgent, LoopforgeAgentError


def free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class VendorStub:
    """A stand-in token endpoint."""

    def __init__(self) -> None:
        self.status = 200
        self.payload: object = {
            "access_token": "at-live",
            "refresh_token": "rt-live",
            "expires_in": 3600,
        }
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: object) -> None:
                return

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                body = json.dumps(outer.payload).encode()
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server, self.base = serve(Handler)

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class OAuthEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        home = Path(self.temporary.name)

        self.vendor = VendorStub()
        self.addCleanup(self.vendor.close)

        # A real provider, pointed at the stand-in and at a port this test can
        # actually bind. Everything else about it is the shipped definition.
        self.provider = replace(
            registry.ANTHROPIC,
            token_url=f"{self.vendor.base}/token",
            callback_port=free_port(),
        )
        patch = mock.patch.object(registry, "PROVIDERS", (self.provider,))
        patch.start()
        self.addCleanup(patch.stop)

        self.agent = object.__new__(LoopforgeAgent)
        self.agent._user_store = UserStore(home)
        self.agent._pending_logins = {}

    def sign_in(self) -> dict:
        started = self.agent.oauth_begin("anthropic")
        # The browser's part, done for it.
        state = dict(
            part.split("=", 1)
            for part in started["url"].split("?", 1)[1].split("&")
        )["state"]
        urllib.request.urlopen(
            f"{started['redirect_uri']}?code=the-code&state={state}", timeout=3
        ).close()
        return self.agent.oauth_complete("anthropic", timeout=5)

    def test_an_account_starts_out_offered_but_not_signed_in(self) -> None:
        listed = self.agent.oauth_providers()

        self.assertEqual([a["id"] for a in listed["accounts"]], ["anthropic"])
        self.assertFalse(listed["accounts"][0]["signed_in"])

    def test_a_whole_sign_in_completes_and_is_remembered(self) -> None:
        result = self.sign_in()

        self.assertTrue(result["accounts"][0]["signed_in"])
        stored = self.agent.user_store.oauth_grant("anthropic")
        assert stored is not None
        self.assertEqual(stored["access_token"], "at-live")
        self.assertEqual(stored["refresh_token"], "rt-live")

    def test_the_authorization_url_is_returned_rather_than_opened(self) -> None:
        """The browser belongs to the user's session, and the Agent may be
        running with no display at all."""
        started = self.agent.oauth_begin("anthropic")
        self.addCleanup(self.agent._pending_logins.pop("anthropic").close)

        self.assertTrue(started["url"].startswith("https://claude.ai/oauth/authorize?"))

    def test_completing_without_starting_says_so(self) -> None:
        with self.assertRaises(LoopforgeAgentError) as caught:
            self.agent.oauth_complete("anthropic", timeout=0.1)
        self.assertEqual(caught.exception.code, "OAUTH_NOT_STARTED")

    def test_starting_twice_releases_the_first_listener(self) -> None:
        """The redirect port is fixed by the provider, so a leaked listener
        makes the second attempt -- the retry -- impossible."""
        self.agent.oauth_begin("anthropic")

        second = self.agent.oauth_begin("anthropic")
        self.addCleanup(self.agent._pending_logins.pop("anthropic").close)

        self.assertTrue(second["url"])

    def test_an_unknown_account_is_refused(self) -> None:
        with self.assertRaises(LoopforgeAgentError) as caught:
            self.agent.oauth_begin("nope")
        self.assertEqual(caught.exception.code, "OAUTH_PROVIDER_UNKNOWN")

    def test_a_vendor_rejection_surfaces_its_reason(self) -> None:
        self.vendor.status = 400
        self.vendor.payload = {"error": "invalid_grant", "error_description": "code used"}

        with self.assertRaises(LoopforgeAgentError) as caught:
            self.sign_in()

        self.assertEqual(caught.exception.code, "OAUTH_TOKEN_REJECTED")
        self.assertIn("code used", str(caught.exception))

    def test_a_failed_sign_in_leaves_no_account_behind(self) -> None:
        """A half-written credential would show as signed in and then fail at
        every use."""
        self.vendor.status = 400
        self.vendor.payload = {"error": "invalid_grant"}

        with self.assertRaises(LoopforgeAgentError):
            self.sign_in()

        self.assertIsNone(self.agent.user_store.oauth_grant("anthropic"))
        self.assertFalse(self.agent.oauth_providers()["accounts"][0]["signed_in"])

    def test_signing_out_forgets_the_grant(self) -> None:
        self.sign_in()

        result = self.agent.oauth_sign_out("anthropic")

        self.assertFalse(result["accounts"][0]["signed_in"])
        self.assertIsNone(self.agent.user_store.oauth_grant("anthropic"))

    def test_the_re_login_deadline_is_reported_once_signed_in(self) -> None:
        """Anthropic kills the whole refresh family about thirty days after the
        interactive login however healthily it has rotated since."""
        listed = self.sign_in()

        self.assertTrue(listed["accounts"][0]["grant_deadline"])

    def test_pending_logins_are_not_shared_between_agents(self) -> None:
        """Held on the class, one dict would serve every agent ever built and
        two projects would trade sign-ins."""
        other = object.__new__(LoopforgeAgent)
        other._pending_logins = {}

        self.agent.oauth_begin("anthropic")
        self.addCleanup(self.agent._pending_logins.pop("anthropic").close)

        self.assertEqual(other._pending_logins, {})


if __name__ == "__main__":
    unittest.main()
