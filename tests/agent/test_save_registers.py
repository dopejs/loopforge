"""Saving an endpoint brings it into service, without ending anything."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from loopforge_agent.application import LoopforgeAgent
from loopforge.userstore import UserStore


class SaveRegistersTheEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.agent = object.__new__(LoopforgeAgent)
        self.agent._user_store = UserStore(Path(self.temporary.name))
        self.agent.runtime = mock.Mock()
        self.agent.runtime.status.return_value = {
            "healthy": True,
            "base_url": "http://127.0.0.1:1",
            "token": "t",
        }
        self.put = mock.Mock()
        client = mock.Mock()
        client.put = self.put
        patch = mock.patch("loopforge_agent.application.KuraClient", return_value=client)
        patch.start()
        self.addCleanup(patch.stop)

    def save(self, **kwargs):
        return self.agent.save_provider_settings(
            "https://api.example.test/v1", "sk-1", "a-model", **kwargs
        )

    def test_a_saved_endpoint_is_registered_rather_than_restarted_into(self) -> None:
        # Reaching for another provider is something a person does during a
        # task. A restart would end whatever run is in flight, which is the
        # one thing they are in the middle of.
        result = self.save()

        self.assertTrue(result["live"])
        self.agent.runtime.stop.assert_not_called()
        path, body = self.put.call_args[0]
        self.assertTrue(path.endswith("/account"))
        self.assertEqual(body["baseURL"], "https://api.example.test/v1")
        self.assertEqual(body["accessToken"], "sk-1")

    def test_an_account_backed_endpoint_carries_its_own_wire_and_token(self) -> None:
        self.agent.user_store.save_oauth_grant(
            {"provider_id": "anthropic", "access_token": "live-token"}
        )

        self.save(oauth_provider_id="anthropic")

        body = self.put.call_args[0][1]
        # The wire is named, not guessed: this one is not OpenAI-compatible.
        self.assertEqual(body["protocol"], "anthropic_messages")
        self.assertEqual(body["accessToken"], "live-token")

    def test_a_runtime_that_cannot_be_reached_does_not_lose_the_endpoint(self) -> None:
        """It was saved either way, and reporting that it is not live yet beats
        discarding what the user just configured."""
        self.agent.runtime.status.return_value = {"healthy": False}

        result = self.save()

        self.assertFalse(result["live"])
        self.assertEqual(
            self.agent.user_store.provider("openai_compatible")["base_url"],
            "https://api.example.test/v1",
        )


if __name__ == "__main__":
    unittest.main()
