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


class ProviderIdentityTests(unittest.TestCase):
    """The fields a picked source needs beyond an endpoint."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.agent = object.__new__(LoopforgeAgent)
        self.agent._user_store = UserStore(Path(self.temporary.name) / "home")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_a_picked_source_keeps_its_name_and_protocol(self) -> None:
        """So the wizard can show what was chosen rather than making the user
        recognise a bare URL."""
        self.agent.save_provider_settings(
            "https://api.deepseek.com/v1",
            "sk-1",
            "deepseek-chat",
            display_name="DeepSeek",
            protocol="openai_compatible",
        )

        result = self.agent.provider_settings()

        self.assertEqual(result["display_name"], "DeepSeek")
        self.assertEqual(result["protocol"], "openai_compatible")

    def test_a_protocol_is_always_present(self) -> None:
        """Every endpoint is spoken to somehow; a blank protocol would say
        nothing about how."""
        self.agent.save_provider_settings("https://x.test/v1", "k", "m")
        self.assertEqual(self.agent.provider_settings()["protocol"], "openai_compatible")


class RoleRoutingTests(unittest.TestCase):
    """Routing lives in Kura; the Agent only forwards."""

    def setUp(self) -> None:
        self.agent = object.__new__(LoopforgeAgent)

        class _Runtime:
            def status(self) -> dict:
                return {"healthy": False, "reason": "not started"}

        self.agent.runtime = _Runtime()

    def test_a_blank_role_is_refused_before_the_runtime(self) -> None:
        for value in ("", "   "):
            with self.subTest(value=value), self.assertRaises(LoopforgeAgentError) as caught:
                self.agent.route_model_role(value, "openai_compatible")
            self.assertEqual(caught.exception.code, "ROLE_INVALID")

    def test_routing_without_a_runtime_says_so(self) -> None:
        """Routing is a runtime capability, so an unstarted runtime is the
        answer rather than a queued change that never lands."""
        with self.assertRaises(LoopforgeAgentError) as caught:
            self.agent.route_model_role("primary", "openai_compatible")
        self.assertEqual(caught.exception.code, "AGENT_NOT_READY")

    def test_clearing_without_a_runtime_says_so(self) -> None:
        with self.assertRaises(LoopforgeAgentError) as caught:
            self.agent.clear_model_role("primary")
        self.assertEqual(caught.exception.code, "AGENT_NOT_READY")


class OperatorSettingsTests(unittest.TestCase):
    """Who the Agent records as the approver.

    This used to live only in the Workbench's local storage, so the Agent could
    not read it and every approval had to carry one in from the front end.
    """

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.agent = object.__new__(LoopforgeAgent)
        self.agent._user_store = UserStore(Path(self.temporary.name) / "home")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_an_unset_operator_is_reported_as_unconfigured(self) -> None:
        result = self.agent.operator_settings()
        self.assertFalse(result["configured"])
        self.assertEqual(result["name"], "")

    def test_saving_mints_an_id_and_keeps_it_across_a_rename(self) -> None:
        """The id is what makes a history of approvals one person."""
        first = self.agent.save_operator_settings("Ada")
        self.assertTrue(first["configured"])
        self.assertTrue(first["id"].startswith("op_"))

        renamed = self.agent.save_operator_settings("Ada L")

        self.assertEqual(renamed["id"], first["id"])
        self.assertEqual(renamed["name"], "Ada L")

    def test_a_blank_name_is_refused(self) -> None:
        """A name is what makes an approval readable months later."""
        for value in ("", "   "):
            with self.subTest(value=value), self.assertRaises(LoopforgeAgentError) as caught:
                self.agent.save_operator_settings(value)
            self.assertEqual(caught.exception.code, "OPERATOR_NAME_INVALID")

    def test_the_stored_operator_fills_in_a_missing_approver(self) -> None:
        """The point of moving it: a caller that supplies nothing still gets a
        named approval instead of a refusal."""
        self.agent.save_operator_settings("Ada")

        resolved = self.agent._resolve_approver(None, None)

        self.assertEqual(resolved[1], "Ada")
        self.assertTrue(resolved[0].startswith("op_"))

    def test_a_supplied_approver_is_not_overridden(self) -> None:
        """The Workbench passes what the user just confirmed; the store must
        not quietly replace it."""
        self.agent.save_operator_settings("Ada")

        self.assertEqual(
            self.agent._resolve_approver("op_other", "Grace"), ("op_other", "Grace")
        )

    def test_without_a_stored_operator_nothing_is_invented(self) -> None:
        """An approver nobody chose would attribute a decision to a
        placeholder; the core's refusal is the correct outcome."""
        self.assertEqual(self.agent._resolve_approver(None, None), (None, None))

    def test_an_unreadable_store_does_not_invent_an_approver(self) -> None:
        import sqlite3

        from loopforge.userstore import SCHEMA_VERSION

        self.agent.save_operator_settings("Ada")
        with sqlite3.connect(self.agent.user_store.path) as connection:
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

        self.assertEqual(self.agent._resolve_approver(None, None), (None, None))


class ApproverFallbackTests(unittest.TestCase):
    """The fallback where it matters: recording something the core checks."""

    def setUp(self) -> None:
        from loopforge.project import HYPOTHESIS_FIELDS, LoopforgeProject

        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.fields = {key: f"value {key}" for key in HYPOTHESIS_FIELDS}
        self.agent = object.__new__(LoopforgeAgent)
        self.agent._user_store = UserStore(root / "home")
        self.agent.project = LoopforgeProject(root / "project")
        self.agent.project.init()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _human_approval(self) -> str:
        return {
            item["code"]: item["status"]
            for item in self.agent.gate("PROTOTYPING")["requirements"]
        }["HUMAN_APPROVAL"]

    def test_a_hypothesis_recorded_without_an_approver_still_opens_the_gate(self) -> None:
        self.agent.save_operator_settings("Ada")

        self.agent.create_hypothesis(self.fields, rationale="Reviewed it.")

        self.assertEqual(self._human_approval(), "satisfied")

    def test_without_a_stored_operator_the_gate_stays_shut(self) -> None:
        """Unchanged behaviour when nobody has been named: the approval is
        refused rather than attributed to no one."""
        self.agent.create_hypothesis(self.fields)
        self.assertEqual(self._human_approval(), "missing")


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
