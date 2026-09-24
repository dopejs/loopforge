"""What the provider panel says about an account.

Kura's `AuthMode` has `none`, `api_key` and `local_cli_bridge` and nothing for
a subscription, so `build_account_profile` hardcodes `api_key` and reports no
secret configured. The panel then said `apiKey: Not configured` about an
Anthropic account that was signed in and answering every request -- which reads
as a broken setup and is the opposite of one.

The Agent is where this is known: it holds the OAuth grant and the provider
record naming it.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from loopforge_agent.application import LoopforgeAgent
from loopforge.userstore import UserStore


class MarkingAccounts(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = UserStore(self.root / "home")
        self.agent = LoopforgeAgent(self.root, kura_binary="/bin/false")
        # Backed by the private slot the property fills on first use, so the
        # test never reaches the real user-level store.
        self.agent._user_store = self.store

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _record(self, provider_id: str, oauth_provider_id: str = "") -> None:
        self.store.save_provider(
            provider_id,
            "https://api.anthropic.com",
            "",
            "claude-sonnet-4-5",
            display_name="Anthropic",
            protocol="anthropic_messages",
            oauth_provider_id=oauth_provider_id,
        )

    def _sign_in(self, provider_id: str) -> None:
        later = datetime.now(UTC) + timedelta(hours=6)
        self.store.save_oauth_grant(
            {
                "provider_id": provider_id,
                "access_token": "t" * 40,
                "refresh_token": "r" * 40,
                "expires_at": later.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "scope": "",
            }
        )

    def _mark(self, providers):
        self.agent._mark_accounts(providers)
        return providers

    def test_an_account_backed_provider_is_not_described_as_a_key(self) -> None:
        # The bug exactly: signed in, answering, and reported as an API key
        # with no secret configured.
        self._record("anthropic", oauth_provider_id="anthropic")
        self._sign_in("anthropic")

        marked = self._mark([{"id": "anthropic", "auth_mode": "api_key", "secret_configured": False}])

        self.assertEqual(marked[0]["auth_mode"], "account")
        self.assertEqual(marked[0]["oauth_provider_id"], "anthropic")
        self.assertTrue(marked[0]["signed_in"])

    def test_an_account_that_is_not_signed_in_says_so(self) -> None:
        # Which is the honest version of "not configured" for this kind of
        # provider: there is nothing to type, only somebody to be.
        self._record("anthropic", oauth_provider_id="anthropic")

        marked = self._mark([{"id": "anthropic", "auth_mode": "api_key"}])

        self.assertEqual(marked[0]["auth_mode"], "account")
        self.assertFalse(marked[0]["signed_in"])

    def test_a_key_backed_provider_is_left_alone(self) -> None:
        # Someone who typed a key should still be told whether it is there.
        self._record("deepseek")

        marked = self._mark([{"id": "deepseek", "auth_mode": "api_key", "secret_configured": True}])

        self.assertEqual(marked[0]["auth_mode"], "api_key")
        self.assertNotIn("oauth_provider_id", marked[0])

    def test_a_provider_the_agent_has_no_record_of_is_left_alone(self) -> None:
        # The runtime can carry providers from its own config. Claiming one is
        # an account would be inventing a sign-in nobody made.
        marked = self._mark([{"id": "echo", "auth_mode": "none"}])

        self.assertEqual(marked[0]["auth_mode"], "none")

    def test_an_unreadable_store_leaves_the_runtime_s_account_standing(self) -> None:
        # Worse, but not wrong in a new way -- and it must not empty the panel.
        def explode() -> list:
            raise RuntimeError("no store")

        self.agent.user_store.providers = explode  # type: ignore[method-assign]
        marked = self._mark([{"id": "anthropic", "auth_mode": "api_key"}])

        self.assertEqual(marked[0]["auth_mode"], "api_key")


class ThroughTheListing(unittest.TestCase):
    """The wiring, not only the marking.

    A first version of this file called `_mark_accounts` directly and nothing
    else. Removing the one line that calls it from `providers()` left every
    test green -- the marking worked and nobody used it.
    """

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = UserStore(self.root / "home")
        self.agent = LoopforgeAgent(self.root, kura_binary="/bin/false")
        self.agent._user_store = self.store
        self.store.save_provider(
            "anthropic",
            "https://api.anthropic.com",
            "",
            "claude-sonnet-4-5",
            display_name="Anthropic",
            protocol="anthropic_messages",
            oauth_provider_id="anthropic",
        )
        later = datetime.now(UTC) + timedelta(hours=6)
        self.store.save_oauth_grant(
            {
                "provider_id": "anthropic",
                "access_token": "t" * 40,
                "refresh_token": "r" * 40,
                "expires_at": later.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "scope": "",
            }
        )

        self.agent.runtime.status = lambda: {  # type: ignore[method-assign]
            "healthy": True,
            "base_url": "http://127.0.0.1:1",
            "token": "t",
        }

        class Client:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def get(self, path, query=None):
                if path == "/v1/providers":
                    return {
                        "items": [
                            {
                                "providerId": "anthropic",
                                "title": "Anthropic",
                                "authMode": "api_key",
                                "secretConfigured": False,
                                "defaultModel": "claude-sonnet-4-5",
                                "health": "ready",
                                "configured": True,
                            }
                        ],
                        "models": {"anthropic": []},
                    }
                return {"items": []}

        import loopforge_agent.application as module

        # Restored in tearDown. This is a module global, and leaving a fake in
        # it made every test that ran afterwards talk to this one's stub --
        # which is how a passing suite started reporting one provider where a
        # live daemon had two.
        self.module = module
        self.real_client = module.KuraClient
        module.KuraClient = Client  # type: ignore[assignment]

    def tearDown(self) -> None:
        self.module.KuraClient = self.real_client
        self.temporary.cleanup()

    def test_the_listing_a_surface_reads_says_it_is_an_account(self) -> None:
        listed = self.agent.providers()["providers"]

        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["auth_mode"], "account")
        self.assertTrue(listed[0]["signed_in"])


if __name__ == "__main__":
    unittest.main()
