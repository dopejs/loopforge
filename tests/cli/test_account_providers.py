"""Handing Kura the subscriptions a user signed into."""
from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from loopforge.agent.supervisor import KuraRuntimeSupervisor
from loopforge.project import LoopforgeProject
from loopforge.userstore import UserStore


class AccountEnvironmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.store = UserStore(root / "store")
        self.supervisor = KuraRuntimeSupervisor(
            LoopforgeProject(root), "kura", user_store=self.store
        )

    def accounts(self) -> list[dict]:
        env = self.supervisor._account_environment()
        return json.loads(env["KURA_LLM_ACCOUNTS"]) if env else []

    def sign_in(self, provider_id: str, token: str = "at") -> None:
        self.store.save_oauth_grant({"provider_id": provider_id, "access_token": token})

    def test_nothing_signed_in_sends_nothing(self) -> None:
        self.assertEqual(self.supervisor._account_environment(), {})

    def test_a_signed_in_account_becomes_a_provider(self) -> None:
        self.sign_in("anthropic", "live-token")

        [account] = self.accounts()

        self.assertEqual(account["id"], "anthropic")
        # The wire is named rather than guessed from the URL: this one is not
        # OpenAI-compatible and routing it as though it were would 404.
        self.assertEqual(account["protocol"], "anthropic_messages")
        self.assertEqual(account["accessToken"], "live-token")
        self.assertTrue(account["baseURL"].startswith("https://"))

    def test_every_signed_in_account_is_sent_at_once(self) -> None:
        """A person holds whichever subscriptions they signed into, and most of
        those vendors need no wire of their own."""
        for provider_id in ("anthropic", "openai_codex", "xai", "zai", "kimi"):
            self.sign_in(provider_id)

        sent = {account["id"]: account["protocol"] for account in self.accounts()}

        self.assertEqual(
            sent,
            {
                "anthropic": "anthropic_messages",
                "openai_codex": "openai_responses",
                "xai": "openai_compatible",
                "zai": "openai_compatible",
                "kimi": "openai_compatible",
            },
        )

    def test_two_providers_coexist_under_their_own_names(self) -> None:
        """Every endpoint used to be written into one slot called
        `openai_compatible`, so adding a second replaced the first and both
        came back under that name."""
        self.store.save_provider(
            "anthropic", "https://api.anthropic.com", "t", "claude-sonnet-4-5",
            display_name="Anthropic", protocol="anthropic_messages",
        )
        self.store.save_provider(
            "deepseek", "https://api.deepseek.com/v1", "sk-1", "deepseek-chat",
            display_name="DeepSeek",
        )

        sent = {account["id"]: account for account in self.accounts()}

        self.assertEqual(sorted(sent), ["anthropic", "deepseek"])
        self.assertEqual(sent["anthropic"]["title"], "Anthropic")
        self.assertEqual(sent["anthropic"]["protocol"], "anthropic_messages")
        self.assertEqual(sent["deepseek"]["protocol"], "openai_compatible")

    def test_a_configured_provider_survives_a_restart(self) -> None:
        """One registered while the daemon runs lives only in its memory. This
        is what the daemon is handed at start, so an endpoint the user added
        does not come back as the built-in slot."""
        self.store.save_provider(
            "anthropic", "https://api.anthropic.com", "t", "claude-sonnet-4-5",
            display_name="Anthropic", protocol="anthropic_messages",
        )

        env = self.supervisor._account_environment()

        self.assertIn("anthropic", env["KURA_LLM_ACCOUNTS"])
        # And something answers a request that names no provider.
        self.assertEqual(env["KURA_LLM_DEFAULT_PROVIDER"], "anthropic")

    def test_a_signed_in_account_does_not_duplicate_a_configured_one(self) -> None:
        """Both describe the same provider id, and two entries for one id
        collide in the daemon's inventory -- which is how a configured endpoint
        ended up displaying the other one's name."""
        self.store.save_provider(
            "anthropic", "https://api.anthropic.com", "t", "claude-sonnet-4-5",
            display_name="Anthropic", protocol="anthropic_messages",
        )
        self.sign_in("anthropic")

        ids = [account["id"] for account in self.accounts()]

        self.assertEqual(ids.count("anthropic"), 1)

    def test_an_account_with_no_dispatch_endpoint_is_left_out(self) -> None:
        """Signing in reads its usage; it is not somewhere a request is routed
        at a guess."""
        self.sign_in("gitlab_duo")

        self.assertEqual(self.accounts(), [])

    def test_an_account_with_no_token_is_left_out(self) -> None:
        self.sign_in("anthropic", "")

        self.assertEqual(self.accounts(), [])

    def test_an_unreadable_store_does_not_stop_the_daemon(self) -> None:
        """A configured endpoint should still work when the account store
        cannot be read."""
        broken = KuraRuntimeSupervisor(
            LoopforgeProject(Path(self.temporary.name)), "kura", user_store=object()
        )

        self.assertEqual(broken._account_environment(), {})


if __name__ == "__main__":
    unittest.main()
