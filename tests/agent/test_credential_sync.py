"""Handing Kura a fresh access token before a dispatch.

The failure this prevents is quiet: a token that expired since the last
dispatch comes back as a 401, which reads like a misconfigured endpoint rather
than an expired session. So the refresh happens before the request, and its
result is reported rather than raised -- an Agent that collapses before
dispatching is worse than one that lets the vendor say what is wrong.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from loopforge.oauth import registry
from loopforge.oauth.flow import Grant
from loopforge.userstore import UserStore
from loopforge_agent.application import LoopforgeAgent


def iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


class CredentialSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = UserStore(Path(self.temporary.name))

        self.agent = object.__new__(LoopforgeAgent)
        self.agent._user_store = self.store
        self.agent.runtime = mock.Mock()
        self.agent.runtime.status.return_value = {
            "healthy": True,
            "base_url": "http://127.0.0.1:1",
            "token": "t",
        }

        self.put = mock.Mock()
        client = mock.Mock()
        client.put = self.put
        patch = mock.patch(
            "loopforge_agent.application.KuraClient", return_value=client
        )
        patch.start()
        self.addCleanup(patch.stop)

    def bind(self, oauth_id: str = "anthropic") -> None:
        self.store.save_provider(
            "openai_compatible",
            "https://api.example.test/v1",
            "stale-token",
            "a-model",
            oauth_provider_id=oauth_id,
        )

    def sign_in(self, expires_at: str, access: str = "live-token") -> None:
        self.store.save_oauth_grant(
            {
                "provider_id": "anthropic",
                "access_token": access,
                "refresh_token": "rt",
                "expires_at": expires_at,
            }
        )

    def test_a_valid_token_is_handed_over_as_it_stands(self) -> None:
        self.bind()
        self.sign_in(iso(datetime.now(timezone.utc) + timedelta(hours=2)))

        result = self.agent.sync_provider_credential()

        self.assertTrue(result["synced"])
        path, body = self.put.call_args[0]
        self.assertEqual(path, "/v1/providers/openai_compatible/credential")
        self.assertEqual(body, {"apiKey": "live-token"})

    def test_a_token_near_expiry_is_refreshed_before_being_sent(self) -> None:
        """Sending one that expires in a minute wastes the dispatch: it is
        valid now and rejected by the time it arrives."""
        self.bind()
        self.sign_in(iso(datetime.now(timezone.utc) + timedelta(minutes=1)), "about-to-die")
        renewed = Grant("anthropic", "renewed-token", "rt2", iso(
            datetime.now(timezone.utc) + timedelta(hours=1)
        ))

        with mock.patch("loopforge.oauth.session.refresh_grant", return_value=renewed):
            result = self.agent.sync_provider_credential()

        self.assertTrue(result["synced"])
        self.assertEqual(self.put.call_args[0][1], {"apiKey": "renewed-token"})
        # And the renewal is kept: a rotated refresh token invalidates the old
        # one at once, so losing it costs the account its next sign-in.
        self.assertEqual(self.store.oauth_grant("anthropic")["refresh_token"], "rt2")

    def test_an_endpoint_using_a_typed_key_is_left_alone(self) -> None:
        """Not every endpoint draws on an account, and doing nothing to one
        that does not is a normal outcome rather than a failure."""
        self.store.save_provider(
            "openai_compatible", "https://api.example.test/v1", "sk-typed", "a-model"
        )

        result = self.agent.sync_provider_credential()

        self.assertFalse(result["synced"])
        self.assertIn("key rather than an account", result["reason"])
        self.put.assert_not_called()

    def test_an_account_that_was_never_signed_in_is_reported_not_raised(self) -> None:
        self.bind()

        result = self.agent.sync_provider_credential()

        self.assertFalse(result["synced"])
        self.assertIn("not signed in", result["reason"])
        self.put.assert_not_called()

    def test_a_failed_refresh_does_not_take_the_dispatch_down_with_it(self) -> None:
        """The vendor's own 401 is a better error than the Agent throwing
        before the request is even attempted."""
        from loopforge.oauth.flow import OAuthError

        self.bind()
        self.sign_in(iso(datetime.now(timezone.utc) - timedelta(minutes=1)))

        with mock.patch(
            "loopforge.oauth.session.refresh_grant",
            side_effect=OAuthError("Refresh token expired", "OAUTH_TOKEN_REJECTED"),
        ):
            result = self.agent.sync_provider_credential()

        self.assertFalse(result["synced"])
        self.assertIn("Refresh token expired", result["reason"])

    def test_an_unready_runtime_is_reported_rather_than_dialled(self) -> None:
        self.bind()
        self.sign_in(iso(datetime.now(timezone.utc) + timedelta(hours=2)))
        self.agent.runtime.status.return_value = {"healthy": False}

        result = self.agent.sync_provider_credential()

        self.assertFalse(result["synced"])
        self.put.assert_not_called()

    def test_the_stored_record_keeps_up_with_what_kura_is_using(self) -> None:
        """So a restart starts from the current token rather than the one the
        endpoint was first configured with."""
        self.bind()
        self.sign_in(iso(datetime.now(timezone.utc) + timedelta(hours=2)))

        self.agent.sync_provider_credential()

        record = self.store.provider("openai_compatible")
        self.assertEqual(record["api_key"], "live-token")
        # The binding survives the rewrite; losing it would turn the endpoint
        # back into a static-key one on the next save.
        self.assertEqual(record["oauth_provider_id"], "anthropic")
        self.assertEqual(record["model"], "a-model")

    def test_an_unknown_account_binding_is_reported(self) -> None:
        self.bind("no-such-vendor")

        result = self.agent.sync_provider_credential()

        self.assertFalse(result["synced"])
        self.assertTrue(result["reason"])


if __name__ == "__main__":
    unittest.main()
