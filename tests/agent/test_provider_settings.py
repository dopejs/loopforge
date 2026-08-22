"""Configuring the OpenAI-compatible endpoint.

Until this existed the Workbench told the user that credentials were managed by
the Agent's configuration and then offered no way to reach it. These tests
cover the two properties that keep the fix from being worse than the gap: the
key is never read back out, and saving one says plainly that it is not live
yet.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from loopforge.userstore import UserStore
from loopforge_agent.application import LoopforgeAgent, LoopforgeAgentError


class ProviderSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.agent = object.__new__(LoopforgeAgent)
        self.agent._user_store = UserStore(Path(self.temporary.name) / "home")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_an_unconfigured_endpoint_reports_itself_as_such(self) -> None:
        result = self.agent.provider_settings()
        self.assertEqual(result["provider_id"], "openai_compatible")
        self.assertFalse(result["configured"])
        self.assertFalse(result["has_api_key"])
        self.assertEqual(result["base_url"], "")

    def test_the_key_is_never_returned(self) -> None:
        """A surface needs to know a credential exists, not what it is.
        Returning it would put it in a response body, a log and a renderer for
        no purpose the user has."""
        self.agent.save_provider_settings("https://api.example.test/v1", "sk-secret", "m")

        result = self.agent.provider_settings()

        self.assertTrue(result["has_api_key"])
        self.assertNotIn("api_key", result)
        self.assertNotIn("sk-secret", str(result))

    def test_saving_says_it_is_not_live_yet(self) -> None:
        """Kura reads its provider configuration at boot. Without this the user
        saves an endpoint and cannot tell why nothing answers."""
        result = self.agent.save_provider_settings(
            "https://api.example.test/v1", "sk-secret", "some-model"
        )
        self.assertTrue(result["restart_required"])
        self.assertTrue(result["configured"])

    def test_an_empty_key_keeps_the_stored_one(self) -> None:
        self.agent.save_provider_settings("https://a.test/v1", "sk-secret", "m1")

        self.agent.save_provider_settings("https://b.test/v1", "", "m2")

        stored = self.agent.user_store.provider("openai_compatible")
        self.assertEqual(stored["api_key"], "sk-secret")
        self.assertEqual(stored["base_url"], "https://b.test/v1")
        self.assertEqual(stored["model"], "m2")

    def test_a_missing_url_or_model_is_refused(self) -> None:
        for url, model in (("", "m"), ("https://x.test", ""), ("  ", "  ")):
            with self.subTest(url=url, model=model), self.assertRaises(
                LoopforgeAgentError
            ) as caught:
                self.agent.save_provider_settings(url, "k", model)
            self.assertEqual(caught.exception.code, "PROVIDER_SETTINGS_INVALID")

    def test_a_non_http_url_is_refused(self) -> None:
        """The value is handed to a daemon that will make requests with it; a
        scheme it cannot use should fail here rather than at dispatch."""
        for url in ("api.example.test/v1", "ftp://x.test", "file:///etc/passwd"):
            with self.subTest(url=url), self.assertRaises(LoopforgeAgentError) as caught:
                self.agent.save_provider_settings(url, "k", "m")
            self.assertEqual(caught.exception.code, "PROVIDER_SETTINGS_INVALID")

    def test_forgetting_clears_it_and_also_needs_a_restart(self) -> None:
        self.agent.save_provider_settings("https://a.test/v1", "sk-secret", "m")

        result = self.agent.forget_provider_settings()

        self.assertFalse(result["configured"])
        self.assertFalse(result["has_api_key"])
        self.assertTrue(result["restart_required"])
        self.assertIsNone(self.agent.user_store.provider("openai_compatible"))


class SupervisorInjectionTests(unittest.TestCase):
    """What the configuration actually does: reach Kura at startup."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = UserStore(self.root / "home")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _supervisor(self):
        from loopforge.agent.supervisor import KuraRuntimeSupervisor
        from loopforge.project import LoopforgeProject

        return KuraRuntimeSupervisor(
            LoopforgeProject(self.root / "project"),
            dope_binary="/bin/false",
            user_store=self.store,
        )

    def test_an_unconfigured_store_injects_nothing(self) -> None:
        """Kura then leaves the endpoint unregistered, so an unconfigured
        daemon reads as unconfigured rather than broken."""
        self.assertEqual(self._supervisor()._provider_environment(), {})

    def test_a_partial_configuration_injects_nothing(self) -> None:
        """Half a provider would register an endpoint that fails every
        dispatch."""
        self.store.save_provider("openai_compatible", "https://a.test/v1", "k", "")
        self.assertEqual(self._supervisor()._provider_environment(), {})

    def test_a_configured_provider_reaches_the_daemon(self) -> None:
        self.store.save_provider(
            "openai_compatible", "https://api.example.test/v1", "sk-secret", "some-model"
        )

        environment = self._supervisor()._provider_environment()

        self.assertEqual(
            environment["KURA_LLM_OPENAI_COMPATIBLE_BASE_URL"],
            "https://api.example.test/v1",
        )
        self.assertEqual(environment["KURA_LLM_OPENAI_COMPATIBLE_API_KEY"], "sk-secret")
        self.assertEqual(environment["KURA_LLM_OPENAI_COMPATIBLE_MODEL"], "some-model")
        # Configuring an endpoint is also choosing it; otherwise chat still
        # answers from the built-in echo provider and looks broken.
        self.assertEqual(environment["KURA_LLM_DEFAULT_PROVIDER"], "openai_compatible")
        # A drafted hypothesis is eleven sections; the default timeout is short.
        self.assertEqual(environment["KURA_LLM_OPENAI_COMPATIBLE_TIMEOUT_MS"], "180000")

    def test_an_unreadable_store_does_not_stop_the_daemon(self) -> None:
        """A store this build cannot read must not prevent a daemon that would
        otherwise run on its built-in provider."""
        import sqlite3

        from loopforge.userstore import SCHEMA_VERSION

        self.store.save_provider("openai_compatible", "https://a.test/v1", "k", "m")
        with sqlite3.connect(self.store.path) as connection:
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

        self.assertEqual(self._supervisor()._provider_environment(), {})


if __name__ == "__main__":
    unittest.main()
