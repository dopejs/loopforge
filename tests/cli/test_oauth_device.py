"""Signing in with a device code, and the payload shapes vendors insist on.

The device flow's whole difficulty is that "not yet" arrives looking like a
failure. A vendor answers a poll with a 4xx and `authorization_pending` for as
long as the user is still typing the code, and `slow_down` when it wants to be
asked less often -- abandon on the first, and the sign-in dies while the user
is halfway through it; ignore the second, and the vendor starts refusing.
"""

from __future__ import annotations

import json
import os
import unittest
import urllib.parse
from dataclasses import replace
from unittest import mock
from http.server import BaseHTTPRequestHandler

from tests.support.httpstub import serve

from loopforge.oauth.flow import (
    Grant,
    OAuthError,
    begin_device_login,
    begin_login,
    complete_login,
    poll_device_login,
)
from loopforge.oauth.registry import GITHUB_COPILOT, GOOGLE_GEMINI, ZAI


class DeviceFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.device_response: object = {
            "device_code": "dev-1",
            "user_code": "WXYZ-1234",
            "verification_uri": "https://github.com/login/device",
            "interval": 1,
            "expires_in": 900,
        }
        #: Successive answers to the poll, so a run of "not yet" can be staged.
        self.token_responses: list[tuple[int, object]] = []
        self.polls = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: object) -> None:
                return

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length).decode("utf-8")
                if self.path.endswith("/device/code"):
                    status, payload = 200, outer.device_response
                else:
                    outer.polls += 1
                    status, payload = (
                        outer.token_responses.pop(0)
                        if outer.token_responses
                        else (200, {"access_token": "at", "expires_in": 60})
                    )
                    outer.last_poll = dict(urllib.parse.parse_qsl(raw))
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server, base = serve(Handler)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.provider = replace(
            GITHUB_COPILOT,
            device_code_url=f"{base}/login/device/code",
            token_url=f"{base}/login/oauth/access_token",
        )

    def test_a_device_code_is_returned_for_the_user_to_type(self) -> None:
        device = begin_device_login(self.provider)

        self.assertEqual(device.user_code, "WXYZ-1234")
        self.assertEqual(device.verification_uri, "https://github.com/login/device")

    def test_the_complete_uri_is_preferred_when_offered(self) -> None:
        """It embeds the code, so the user does not have to retype it."""
        self.device_response = {
            "device_code": "d",
            "user_code": "ABCD",
            "verification_uri": "https://example.test/device",
            "verification_uri_complete": "https://example.test/device?user_code=ABCD",
        }

        device = begin_device_login(self.provider)

        self.assertEqual(device.verification_uri, "https://example.test/device?user_code=ABCD")

    def test_a_pending_approval_is_waited_out_rather_than_treated_as_failure(self) -> None:
        """The user is still typing the code. Giving up here kills a sign-in
        that was going to succeed."""
        self.token_responses = [
            (400, {"error": "authorization_pending"}),
            (400, {"error": "authorization_pending"}),
            (200, {"access_token": "at-approved", "refresh_token": "rt", "expires_in": 60}),
        ]
        device = replace(begin_device_login(self.provider), interval=1)

        grant = poll_device_login(self.provider, device, timeout=20)

        self.assertEqual(grant.access_token, "at-approved")
        self.assertEqual(self.polls, 3)

    def test_slow_down_actually_slows_the_polling(self) -> None:
        """Ignoring it makes the vendor start refusing outright."""
        self.token_responses = [
            (200, {"error": "slow_down"}),
            (200, {"access_token": "at", "expires_in": 60}),
        ]
        device = replace(begin_device_login(self.provider), interval=1)

        import time

        started = time.monotonic()
        poll_device_login(self.provider, device, timeout=30)
        elapsed = time.monotonic() - started

        # Was 1s; the back-off must have raised it well past that.
        self.assertGreater(elapsed, 4.0)

    def test_slow_down_delivered_as_an_error_status_also_backs_off(self) -> None:
        """Vendors split on this: some answer 200 with an error body, some a
        4xx. Handling only one leaves the other polling at full speed until
        the vendor starts refusing outright."""
        self.token_responses = [
            (400, {"error": "slow_down"}),
            (200, {"access_token": "at", "expires_in": 60}),
        ]
        device = replace(begin_device_login(self.provider), interval=1)

        import time

        started = time.monotonic()
        poll_device_login(self.provider, device, timeout=30)

        self.assertGreater(time.monotonic() - started, 4.0)

    def test_a_real_refusal_stops_the_poll(self) -> None:
        self.token_responses = [(400, {"error": "access_denied"})]
        device = begin_device_login(self.provider)

        with self.assertRaises(OAuthError) as caught:
            poll_device_login(self.provider, device, timeout=10)

        self.assertEqual(caught.exception.code, "OAUTH_DENIED")

    def test_the_poll_gives_up_when_the_code_expires(self) -> None:
        self.token_responses = [(400, {"error": "authorization_pending"})] * 50
        device = replace(begin_device_login(self.provider), interval=1)

        with self.assertRaises(OAuthError) as caught:
            poll_device_login(self.provider, device, timeout=2)

        self.assertEqual(caught.exception.code, "OAUTH_TIMEOUT")

    def test_a_callback_provider_is_not_polled_by_mistake(self) -> None:
        with self.assertRaises(OAuthError) as caught:
            begin_device_login(GOOGLE_GEMINI)
        self.assertEqual(caught.exception.code, "OAUTH_FLOW_MISMATCH")


class TokenPayloadTests(unittest.TestCase):
    """What each vendor requires in, or refuses from, a token request."""

    def setUp(self) -> None:
        self.body: dict[str, str] = {}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: object) -> None:
                return

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length).decode("utf-8")
                outer.body = (
                    json.loads(raw)
                    if "json" in (self.headers.get("Content-Type") or "")
                    else dict(urllib.parse.parse_qsl(raw))
                )
                payload = json.dumps({"access_token": "at", "expires_in": 60}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server, self.base = serve(Handler)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def free_port(self) -> int:
        import socket

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def exchange(self, provider) -> None:
        target = replace(
            provider, token_url=f"{self.base}/token", callback_port=self.free_port()
        )
        pending = begin_login(target)
        self.addCleanup(pending.close)
        complete_login(pending, "code")

    def test_google_sends_the_supplied_client_secret(self) -> None:
        """Its token endpoint refuses the exchange without one.

        Supplied through the environment rather than compiled in: the value is
        Google's, for Google's application, and this repository is public.
        """
        with mock.patch.dict(
            os.environ,
            {
                "LOOPFORGE_GOOGLE_GEMINI_CLIENT_ID": "an-id",
                "LOOPFORGE_GOOGLE_GEMINI_CLIENT_SECRET": "a-secret",
            },
        ):
            self.exchange(GOOGLE_GEMINI)

        self.assertEqual(self.body["client_secret"], "a-secret")
        self.assertEqual(self.body["client_id"], "an-id")

    def test_google_asks_for_offline_access_or_there_is_no_refresh_token(self) -> None:
        """Without it the account silently stops working an hour after it is
        added, which is far from where the mistake was made."""
        self.assertEqual(GOOGLE_GEMINI.extra_authorize_params["access_type"], "offline")
        self.assertEqual(GOOGLE_GEMINI.extra_authorize_params["prompt"], "consent")

    def test_zai_gets_its_own_shape_and_none_of_the_standard_extras(self) -> None:
        """It names the account in the body and refuses the client id and
        verifier a standard exchange would carry."""
        self.exchange(ZAI)

        self.assertEqual(self.body["provider"], "zai")
        self.assertNotIn("client_id", self.body)
        self.assertNotIn("code_verifier", self.body)

    def test_a_provider_that_rejects_pkce_is_not_sent_a_challenge(self) -> None:
        target = replace(ZAI, callback_port=self.free_port())
        pending = begin_login(target)
        self.addCleanup(pending.close)

        self.assertNotIn("code_challenge", pending.url)

    def test_every_other_provider_still_uses_pkce(self) -> None:
        """Turning it off is a per-vendor concession, never a default: without
        it nothing binds an intercepted code to this process."""
        from loopforge.oauth.registry import providers

        without = [p.id for p in providers() if not p.use_pkce]
        self.assertEqual(without, ["zai"])


if __name__ == "__main__":
    unittest.main()
