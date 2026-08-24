"""Providers configured before the daemon starts.

The whole chain, against a real daemon: what the user store holds becomes the
environment the supervisor builds, becomes the daemon's configuration, becomes
`/v1/providers`, becomes what the Workbench lists.

Nothing covered this end to end, and the gap was exactly the size of the bug.
Kura registered the configured accounts with its dispatcher at startup and left
them out of the provider manager's inventory, so a request reached the vendor
while the settings page said no provider existed -- next to a default provider
whose name appeared in no list. The manager's own unit tests passed, because
the manager was only half of it.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from loopforge.userstore import UserStore
from loopforge_agent.application import LoopforgeAgent

from tests.support.kura_daemon import KuraDaemon, requires_kura


@requires_kura
class StartupProviderInventoryTests(unittest.TestCase):
    """A provider the user configured is one the runtime reports."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        store = UserStore(Path(cls.temporary.name) / "home")
        store.save_provider(
            "anthropic",
            "https://api.anthropic.test",
            "sk-not-a-real-key",
            "claude-sonnet-4-5",
            display_name="Anthropic",
            protocol="anthropic_messages",
        )
        store.save_provider(
            "zhipu",
            "https://open.bigmodel.test/api/paas/v4",
            "sk-not-a-real-key",
            "glm-4",
            display_name="Zhipu GLM",
            protocol="openai_compatible",
        )

        from loopforge.agent.supervisor import KuraRuntimeSupervisor
        from loopforge.project import LoopforgeProject

        supervisor = KuraRuntimeSupervisor(
            LoopforgeProject(Path(cls.temporary.name) / "project"),
            dope_binary="/bin/false",
            user_store=store,
        )
        # The real thing the real supervisor would hand the real daemon.
        cls.environment = supervisor._account_environment()
        cls.daemon = KuraDaemon(environment=cls.environment).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.daemon.stop()
        cls.temporary.cleanup()

    def test_the_supervisor_sends_both_providers(self) -> None:
        accounts = json.loads(self.environment["KURA_LLM_ACCOUNTS"])
        self.assertEqual(
            sorted(account["id"] for account in accounts), ["anthropic", "zhipu"]
        )

    def test_the_daemon_lists_what_it_was_configured_with(self) -> None:
        items = self.daemon.client().get("/v1/providers").get("items") or []
        listed = sorted(str(item.get("providerId") or "") for item in items)

        # Both, under their own ids. This answered with an empty list.
        self.assertEqual(listed, ["anthropic", "zhipu"])

    def test_each_provider_keeps_its_own_name_and_wire(self) -> None:
        items = self.daemon.client().get("/v1/providers").get("items") or []
        by_id = {str(item.get("providerId") or ""): item for item in items}

        self.assertEqual(by_id["anthropic"]["title"], "Anthropic")
        # Reported as `openai_compatible` regardless, which is the label a
        # surface puts beside the provider's name.
        self.assertEqual(by_id["anthropic"]["family"], "anthropic_messages")
        self.assertEqual(by_id["zhipu"]["family"], "openai_compatible")

    def test_the_default_provider_is_one_that_exists(self) -> None:
        items = self.daemon.client().get("/v1/providers").get("items") or []
        listed = {str(item.get("providerId") or "") for item in items}

        self.assertIn(self.environment["KURA_LLM_DEFAULT_PROVIDER"], listed)

    def test_the_agent_projects_them_to_the_workbench(self) -> None:
        """The last hop: what the settings page actually renders."""
        agent = object.__new__(LoopforgeAgent)
        agent.runtime = _Runtime(self.daemon.base_url, self.daemon.token)

        inventory = agent.providers()

        self.assertEqual(
            sorted(provider["id"] for provider in inventory["providers"]),
            ["anthropic", "zhipu"],
        )
        self.assertNotIn("reason", inventory)


class _Runtime:
    """The runtime status the Agent reads, pointed at the test daemon."""

    def __init__(self, base_url: str, token: str | None) -> None:
        self._status = {"healthy": True, "base_url": base_url, "token": token}

    def status(self) -> dict:
        return dict(self._status)
