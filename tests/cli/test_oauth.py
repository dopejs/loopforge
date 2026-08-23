"""Signing into an account.

Run against real sockets and a real HTTP server rather than mocks: the parts
that break here are wire-level -- a redirect that lands on the wrong path, a
callback carrying somebody else's state, a token endpoint answering 400 with
the reason in the body -- and a stub would only confirm the shape already
assumed.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import unittest
import urllib.parse
import urllib.request
from dataclasses import replace
from unittest import mock
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler

from tests.support.httpstub import serve

from loopforge.oauth.flow import (
    Grant,
    OAuthError,
    begin_login,
    complete_login,
    grant_deadline,
    needs_refresh,
    refresh_grant,
)
from loopforge.oauth.registry import ANTHROPIC, OPENAI_CODEX, provider


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def visit(url: str) -> int:
    with urllib.request.urlopen(url, timeout=3) as response:
        return int(response.status)


class RegistryTests(unittest.TestCase):
    def test_the_anthropic_client_is_the_one_that_can_run_a_model(self) -> None:
        """`platform.claude.com` issues console tokens without `user:inference`.

        A credential minted there authorises nothing this application wants, so
        the authorization host and the scope are both wire contracts.
        """
        self.assertEqual(
            urllib.parse.urlparse(ANTHROPIC.authorize_url).netloc, "claude.ai"
        )
        self.assertIn("user:inference", ANTHROPIC.scopes)

    def test_the_codex_redirect_port_is_the_registered_one(self) -> None:
        """Registered as exactly this; a different port fails the exchange with
        a 403 that says nothing about ports."""
        self.assertEqual(OPENAI_CODEX.redirect_uri, "http://localhost:1455/callback")

    def test_every_provider_carries_what_its_flow_needs(self) -> None:
        """A missing field does not degrade -- the vendor refuses the exchange
        outright -- so the gap is worth catching here rather than at a user's
        first sign-in."""
        from loopforge.oauth.registry import providers

        for candidate in providers():
            with self.subTest(provider=candidate.id):
                # Either in source or named in the environment: the Google
                # clients are supplied by whoever runs this, so an empty
                # literal is a valid state and a missing pair is not.
                self.assertTrue(
                    candidate.client_id or candidate.client_id_env,
                    "needs a client id, or somewhere to read one from",
                )
                self.assertTrue(candidate.token_url.startswith("https://"))
                if candidate.flow == "device_code":
                    self.assertTrue(
                        candidate.device_code_url.startswith("https://"),
                        "a device flow has nowhere to ask for a code without one",
                    )
                    self.assertEqual(candidate.callback_port, 0, "no redirect to bind")
                else:
                    self.assertGreater(
                        candidate.callback_port, 0, "a redirect flow needs a port"
                    )
                    self.assertTrue(candidate.authorize_url.startswith("https://"))

    def test_googles_clients_carry_the_secret_its_endpoint_demands(self) -> None:
        """Google's token endpoint refuses an installed-app exchange without
        one. It is not a secret in any useful sense -- it ships inside a
        desktop client anyone can read -- but leaving it out means the account
        cannot be signed in at all."""
        from loopforge.oauth.registry import providers

        google = [
            candidate
            for candidate in providers()
            if candidate.token_url.startswith("https://oauth2.googleapis.com/")
        ]
        self.assertTrue(google, "expected at least one Google-hosted client")
        for candidate in google:
            with self.subTest(provider=candidate.id):
                self.assertTrue(
                    candidate.client_secret or candidate.client_secret_env,
                    "Google refuses the exchange without one",
                )
                # And without offline access it issues no refresh token, so
                # the account stops working an hour after it is added.
                self.assertEqual(
                    candidate.extra_authorize_params.get("access_type"), "offline"
                )

    def test_no_two_providers_want_the_same_redirect_port(self) -> None:
        """Each port is fixed by its vendor, so a collision is not something
        that can be resolved at runtime -- one of the two simply cannot sign
        in while the other is mid-flow."""
        from loopforge.oauth.registry import providers

        ports = [p.callback_port for p in providers() if p.callback_port]
        self.assertEqual(len(ports), len(set(ports)), f"duplicate ports in {ports}")

    def test_provider_ids_are_unique(self) -> None:
        from loopforge.oauth.registry import providers

        ids = [p.id for p in providers()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_googles_credentials_are_not_published_in_this_repository(self) -> None:
        """They are Google's, for Google's application, and this repository is
        public. Read from the environment instead, which is also what stops a
        secret scanner from having to decide."""
        from loopforge.oauth.registry import GOOGLE_ANTIGRAVITY, GOOGLE_GEMINI

        for candidate in (GOOGLE_GEMINI, GOOGLE_ANTIGRAVITY):
            with self.subTest(provider=candidate.id):
                self.assertEqual(candidate.client_id, "")
                self.assertEqual(candidate.client_secret, "")
                self.assertTrue(candidate.client_id_env)

    def test_an_account_without_its_credentials_says_what_is_missing(self) -> None:
        """Rather than sending the user to a page that will reject them."""
        from loopforge.oauth.registry import GOOGLE_GEMINI

        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(GOOGLE_GEMINI.configured)
            with self.assertRaises(OAuthError) as caught:
                begin_login(GOOGLE_GEMINI)

        self.assertEqual(caught.exception.code, "OAUTH_CLIENT_UNCONFIGURED")
        self.assertIn("LOOPFORGE_GOOGLE_GEMINI_CLIENT_ID", str(caught.exception))

    def test_a_supplied_pair_is_picked_up_from_the_environment(self) -> None:
        from loopforge.oauth.registry import GOOGLE_GEMINI

        with mock.patch.dict(
            os.environ,
            {
                "LOOPFORGE_GOOGLE_GEMINI_CLIENT_ID": "supplied-id",
                "LOOPFORGE_GOOGLE_GEMINI_CLIENT_SECRET": "supplied-secret",
            },
        ):
            self.assertTrue(GOOGLE_GEMINI.configured)
            self.assertEqual(GOOGLE_GEMINI.resolved_client_id, "supplied-id")
            self.assertEqual(GOOGLE_GEMINI.resolved_client_secret, "supplied-secret")

    def test_an_unknown_provider_is_refused_rather_than_returning_nothing(self) -> None:
        with self.assertRaises(KeyError):
            provider("nope")


class LoginFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = replace(ANTHROPIC, callback_port=free_port())

    def test_the_authorization_url_carries_pkce_and_the_exact_redirect(self) -> None:
        pending = begin_login(self.provider)
        self.addCleanup(pending.close)

        query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(pending.url).query))

        self.assertEqual(query["code_challenge_method"], "S256")
        self.assertEqual(query["redirect_uri"], self.provider.redirect_uri)
        self.assertEqual(query["client_id"], self.provider.client_id)
        # The challenge is sent; the verifier never leaves this process until
        # the exchange, which is the whole point of the exchange being bound.
        self.assertNotIn(pending.pkce.verifier, pending.url)

    def test_a_callback_with_the_right_state_yields_the_code(self) -> None:
        pending = begin_login(self.provider)

        visit(f"{self.provider.redirect_uri}?code=abc123&state={pending.state}")

        self.assertEqual(pending.wait(timeout=3), "abc123")

    def test_a_callback_carrying_someone_elses_state_is_refused(self) -> None:
        """Without this check any page the user happens to visit could drive a
        code of its choosing into the listener."""
        pending = begin_login(self.provider)

        visit(f"{self.provider.redirect_uri}?code=attacker&state=not-the-one")

        with self.assertRaises(OAuthError) as caught:
            pending.wait(timeout=3)
        self.assertEqual(caught.exception.code, "OAUTH_DENIED")

    def test_a_refusal_from_the_provider_is_reported_as_one(self) -> None:
        pending = begin_login(self.provider)

        visit(f"{self.provider.redirect_uri}?error=access_denied&state={pending.state}")

        with self.assertRaises(OAuthError) as caught:
            pending.wait(timeout=3)
        self.assertEqual(caught.exception.code, "OAUTH_DENIED")

    def test_an_unrelated_path_does_not_complete_the_login(self) -> None:
        pending = begin_login(self.provider)
        self.addCleanup(pending.close)

        with self.assertRaises(urllib.error.HTTPError) as caught:
            visit(f"http://localhost:{self.provider.callback_port}/favicon.ico")

        self.assertEqual(caught.exception.code, 404)

    def test_waiting_gives_up_rather_than_hanging_forever(self) -> None:
        pending = begin_login(self.provider)

        with self.assertRaises(OAuthError) as caught:
            pending.wait(timeout=0.2)
        self.assertEqual(caught.exception.code, "OAUTH_TIMEOUT")

    def test_the_listener_is_released_afterwards(self) -> None:
        """The port is fixed by the provider, so a leaked listener makes every
        later sign-in for that account fail."""
        pending = begin_login(self.provider)
        visit(f"{self.provider.redirect_uri}?code=x&state={pending.state}")
        pending.wait(timeout=3)

        second = begin_login(self.provider)
        second.close()

    def test_a_held_port_is_named_rather_than_silently_rebound(self) -> None:
        """Rebinding elsewhere would fail much later, at the exchange, with a
        403 that never mentions a port."""
        first = begin_login(self.provider)
        self.addCleanup(first.close)

        with self.assertRaises(OAuthError) as caught:
            begin_login(self.provider)

        self.assertEqual(caught.exception.code, "OAUTH_PORT_UNAVAILABLE")
        self.assertIn(str(self.provider.callback_port), str(caught.exception))


class TokenEndpointTests(unittest.TestCase):
    """Against a stand-in endpoint, so the request body is what is checked."""

    def setUp(self) -> None:
        self.received: dict[str, object] = {}
        self.status = 200
        self.payload: object = {
            "access_token": "at-1",
            "refresh_token": "rt-2",
            "expires_in": 3600,
            "scope": "user:inference",
        }
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: object) -> None:
                return

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length).decode("utf-8")
                outer.received["content_type"] = self.headers.get("Content-Type", "")
                outer.received["raw"] = raw
                outer.received["body"] = (
                    json.loads(raw)
                    if "json" in str(outer.received["content_type"])
                    else dict(urllib.parse.parse_qsl(raw))
                )
                body = json.dumps(outer.payload).encode()
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server, base = serve(Handler)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.token_url = f"http://127.0.0.1:{self.server.server_port}/token"

    def make(self, **overrides: object):
        return replace(
            ANTHROPIC,
            token_url=self.token_url,
            callback_port=free_port(),
            **overrides,  # type: ignore[arg-type]
        )

    def test_the_exchange_sends_the_verifier_and_the_same_redirect(self) -> None:
        target = self.make()
        pending = begin_login(target)
        self.addCleanup(pending.close)

        grant = complete_login(pending, "the-code")

        body = self.received["body"]
        assert isinstance(body, dict)
        self.assertEqual(body["grant_type"], "authorization_code")
        self.assertEqual(body["code_verifier"], pending.pkce.verifier)
        # Must match the authorization request exactly or the vendor 403s.
        self.assertEqual(body["redirect_uri"], target.redirect_uri)
        self.assertEqual(grant.access_token, "at-1")
        self.assertTrue(grant.expires_at)
        self.assertTrue(grant.authorized_at)

    def test_a_code_with_a_fragment_is_sent_bare(self) -> None:
        """Some vendors hand back `code#state`, which the exchange rejects."""
        pending = begin_login(self.make())
        self.addCleanup(pending.close)

        complete_login(pending, "the-code#the-state")

        body = self.received["body"]
        assert isinstance(body, dict)
        self.assertEqual(body["code"], "the-code")

    def test_the_body_encoding_follows_the_provider(self) -> None:
        """Anthropic wants JSON; the OAuth default is form encoding, and a
        vendor given the wrong one answers 400."""
        pending = begin_login(self.make(token_json_body=True))
        self.addCleanup(pending.close)
        complete_login(pending, "c")
        self.assertIn("json", str(self.received["content_type"]))

        pending = begin_login(self.make(token_json_body=False))
        self.addCleanup(pending.close)
        complete_login(pending, "c")
        self.assertIn("form-urlencoded", str(self.received["content_type"]))

    def test_a_rejection_carries_the_reason_not_just_the_status(self) -> None:
        """"HTTP 400" cannot tell a stale refresh token from a wrong redirect
        URI, and the two need different fixes."""
        self.status = 400
        self.payload = {"error": "invalid_grant", "error_description": "Refresh token expired"}
        target = self.make()

        with self.assertRaises(OAuthError) as caught:
            refresh_grant(target, Grant(target.id, "at", "rt", ""))

        self.assertEqual(caught.exception.code, "OAUTH_TOKEN_REJECTED")
        self.assertIn("Refresh token expired", str(caught.exception))

    def test_a_refresh_keeps_what_the_response_leaves_out(self) -> None:
        """Vendors omit unchanged fields. Treating an omission as a deletion
        strips the account of its identity on the first renewal."""
        self.payload = {"access_token": "at-new", "expires_in": 3600}
        target = self.make()
        existing = Grant(
            provider_id=target.id,
            access_token="at-old",
            refresh_token="rt-keep",
            expires_at="",
            scope="user:inference",
            account_label="someone@example.test",
            org_id="org-1",
            authorized_at="2026-08-01T00:00:00Z",
        )

        renewed = refresh_grant(target, existing)

        self.assertEqual(renewed.access_token, "at-new")
        self.assertEqual(renewed.refresh_token, "rt-keep")
        self.assertEqual(renewed.account_label, "someone@example.test")
        self.assertEqual(renewed.org_id, "org-1")
        # The interactive login anchors an absolute deadline, so a refresh
        # must not move it.
        self.assertEqual(renewed.authorized_at, "2026-08-01T00:00:00Z")

    def test_a_rotated_refresh_token_replaces_the_old_one(self) -> None:
        self.payload = {"access_token": "at", "refresh_token": "rt-rotated", "expires_in": 60}
        target = self.make()

        renewed = refresh_grant(target, Grant(target.id, "a", "rt-old", ""))

        self.assertEqual(renewed.refresh_token, "rt-rotated")

    def test_an_account_with_no_refresh_token_says_to_sign_in_again(self) -> None:
        target = self.make()
        with self.assertRaises(OAuthError) as caught:
            refresh_grant(target, Grant(target.id, "at", "", ""))
        self.assertEqual(caught.exception.code, "OAUTH_NO_REFRESH_TOKEN")


class ExpiryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)

    def grant(self, expires_at: str) -> Grant:
        return Grant("anthropic", "at", "rt", expires_at)

    def test_a_token_expiring_within_the_skew_is_renewed_early(self) -> None:
        """A token valid "now" can still be rejected by the time the request
        arrives, and a refresh is cheaper than a failed dispatch."""
        soon = (self.now + timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
        self.assertTrue(needs_refresh(self.grant(soon), self.now))

    def test_a_token_with_time_left_is_not_renewed(self) -> None:
        later = (self.now + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        self.assertFalse(needs_refresh(self.grant(later), self.now))

    def test_a_token_with_no_stated_expiry_is_left_alone(self) -> None:
        """Refreshing on every use would burn the rotation budget for nothing."""
        self.assertFalse(needs_refresh(self.grant(""), self.now))

    def test_anthropic_grants_carry_an_absolute_deadline(self) -> None:
        """The refresh family dies about thirty days after the interactive
        login however healthily it has rotated since."""
        deadline = grant_deadline(
            ANTHROPIC, Grant("anthropic", "at", "rt", "", authorized_at="2026-08-01T00:00:00Z")
        )
        self.assertEqual(deadline, "2026-08-31T00:00:00Z")

    def test_a_provider_without_such_a_cap_reports_none(self) -> None:
        self.assertEqual(
            grant_deadline(OPENAI_CODEX, Grant("openai_codex", "a", "r", "",
                                               authorized_at="2026-08-01T00:00:00Z")),
            "",
        )


if __name__ == "__main__":
    unittest.main()
