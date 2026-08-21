from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from loopforge.agent.kura_client import KuraAgentError
from loopforge_agent.application import LoopforgeAgent, LoopforgeAgentError


class LoopforgeAgentApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = Mock()
        self.runtime.context.return_value = {
            "schema_version": "game-project-context-v1",
            "project_id": "gameproj_test",
            "project_root": "/tmp/game",
            "observed_revision": 2,
            "stage": "PROTOTYPING",
            "engine": "godot",
            "capabilities": ["loopforge.status"],
            "next_actions": ["run build"],
            "redactions": ["access_tokens"],
        }
        self.agent = object.__new__(LoopforgeAgent)
        self.agent.runtime = self.runtime

    def test_status_exposes_agent_boundary_with_nested_generic_runtime(self) -> None:
        self.runtime.status.return_value = {
            "healthy": True,
            "base_url": "http://127.0.0.1:19192",
        }

        status = self.agent.status()

        self.assertEqual(status["schema_version"], "loopforge-agent-status-v1")
        self.assertTrue(status["ready"])
        self.assertEqual(status["project"]["stage"], "PROTOTYPING")
        self.assertNotIn("base_url", status)
        self.assertNotIn("base_url", status["runtime"])

    def test_query_adds_loopforge_context_before_delegating_to_kura(self) -> None:
        self.runtime.status.return_value = {
            "healthy": True,
            "base_url": "http://127.0.0.1:19192",
        }
        self.runtime.sync_context.return_value = {
            "context": self.runtime.context.return_value
        }
        client = Mock()
        client.post.return_value = {
            "reply": "Inspect the movement loop.",
            "threadId": "thread_1",
        }

        with patch("loopforge_agent.application.KuraClient", return_value=client):
            response = self.agent.query("What should we test?", "thread_1")

        request = client.post.call_args.args[1]
        self.assertEqual(client.post.call_args.args[0], "/v1/chat/query")
        self.assertNotIn("skills", request)
        self.assertIn("Loopforge Router", request["query"])
        self.assertIn("game-project-context-v1", request["query"])
        self.assertIn("What should we test?", request["query"])
        self.assertEqual(request["threadId"], "thread_1")
        self.assertEqual(response["reply"], "Inspect the movement loop.")

    def test_query_requires_a_ready_runtime(self) -> None:
        self.runtime.status.return_value = {"healthy": False}

        with self.assertRaisesRegex(LoopforgeAgentError, "not ready"):
            self.agent.query("Inspect the project")

    def test_manifest_proves_internal_router_is_available(self) -> None:
        manifest = self.agent.manifest()
        self.assertEqual(manifest["schema_version"], "loopforge-agent-manifest-v1")
        self.assertEqual(manifest["skills"][0]["name"], "loopforge-router")
        self.assertEqual(len(manifest["skills"][0]["sha256"]), 64)


def _kura_provider(**overrides: object) -> dict:
    entry = {
        "providerId": "anthropic",
        "title": "Anthropic",
        "family": "anthropic",
        "authMode": "api_key",
        "source": "builtin",
        "modelSelectionMode": "explicit",
        "registered": True,
        "configured": True,
        "ready": True,
        "default": True,
        "baseURL": "https://api.anthropic.com/v1",
        "effectiveTimeoutMs": 60000,
        "effectiveMaxRetries": 3,
        "secretConfigured": True,
        "capabilities": {"chat": True, "vision": True, "embed": False},
    }
    entry.update(overrides)
    return entry


class LoopforgeAgentProviderTests(unittest.TestCase):
    """The provider inventory is a read-only projection of Kura's own
    provider capability; Loopforge stores no provider state of its own."""

    def setUp(self) -> None:
        self.runtime = Mock()
        self.agent = object.__new__(LoopforgeAgent)
        self.agent.runtime = self.runtime

    def _client_returning(self, responses: dict[str, dict]) -> Mock:
        client = Mock()

        def _get(path: str, query: dict | None = None) -> dict:
            # An unstubbed route stands for one the runtime does not serve,
            # which surfaces as a client error rather than a KeyError.
            if path not in responses:
                raise KuraAgentError(f"no route {path}")
            return responses[path]

        client.get.side_effect = _get
        return client

    def test_reports_reason_when_runtime_is_not_ready(self) -> None:
        self.runtime.status.return_value = {"healthy": False, "reason": "not running"}
        result = self.agent.providers()
        self.assertEqual(result["schema_version"], "loopforge-provider-v1")
        self.assertEqual(result["providers"], [])
        self.assertEqual(result["reason"], "not running")

    def test_projects_kura_inventory_into_the_loopforge_contract(self) -> None:
        self.runtime.status.return_value = {
            "healthy": True,
            "base_url": "http://127.0.0.1:19192",
        }
        client = self._client_returning(
            {
                "/v1/providers": {"items": [_kura_provider()]},
                "/v1/providers/anthropic/models": {
                    "items": [
                        {
                            "providerId": "anthropic",
                            "modelId": "claude-sonnet",
                            "displayName": "Claude Sonnet",
                            "default": True,
                            "available": True,
                            "source": "builtin",
                            "chat": True,
                            "stream": True,
                            "coding": True,
                            "toolUse": True,
                        }
                    ]
                },
            }
        )
        with patch(
            "loopforge_agent.application.KuraClient", return_value=client
        ):
            result = self.agent.providers()

        self.assertNotIn("reason", result)
        provider = result["providers"][0]
        self.assertEqual(provider["id"], "anthropic")
        self.assertEqual(provider["health"], "ready")
        self.assertEqual(provider["base_url"], "https://api.anthropic.com/v1")
        self.assertEqual(provider["timeout_ms"], 60000)
        self.assertEqual(provider["max_retries"], 3)
        self.assertEqual(provider["capabilities"], ["chat", "vision"])
        model = provider["models"][0]
        self.assertEqual(model["id"], "claude-sonnet")
        self.assertEqual(model["capabilities"], ["chat", "stream", "coding", "tools"])

    def test_omits_fields_kura_does_not_model(self) -> None:
        """Budgets, custom headers and sampling knobs are not Kura provider
        fields; projecting them would invent Loopforge-side provider state."""
        self.runtime.status.return_value = {
            "healthy": True,
            "base_url": "http://127.0.0.1:19192",
        }
        client = self._client_returning(
            {
                "/v1/providers": {"items": [_kura_provider()]},
                "/v1/providers/anthropic/models": {"items": []},
            }
        )
        with patch("loopforge_agent.application.KuraClient", return_value=client):
            provider = self.agent.providers()["providers"][0]

        for absent in ("budget", "headers", "temperature", "top_p", "parallel_runs"):
            self.assertNotIn(absent, provider)

    def test_derives_health_from_readiness_and_issues(self) -> None:
        self.runtime.status.return_value = {
            "healthy": True,
            "base_url": "http://127.0.0.1:19192",
        }
        entries = [
            _kura_provider(providerId="a", ready=False, issues=["401 unauthorized"]),
            _kura_provider(providerId="b", ready=False, issues=[]),
        ]
        client = Mock()
        client.get.side_effect = lambda path, query=None: (
            {"items": entries} if path == "/v1/providers" else {"items": []}
        )
        with patch("loopforge_agent.application.KuraClient", return_value=client):
            providers = self.agent.providers()["providers"]

        self.assertEqual(
            {p["id"]: p["health"] for p in providers},
            {"a": "error", "b": "unconfigured"},
        )

    def test_model_failure_degrades_one_provider_not_the_inventory(self) -> None:
        self.runtime.status.return_value = {
            "healthy": True,
            "base_url": "http://127.0.0.1:19192",
        }

        def _get(path: str, query: dict | None = None) -> dict:
            if path == "/v1/providers":
                return {"items": [_kura_provider()]}
            raise KuraAgentError("models unavailable")

        client = Mock()
        client.get.side_effect = _get
        with patch("loopforge_agent.application.KuraClient", return_value=client):
            provider = self.agent.providers()["providers"][0]

        self.assertEqual(provider["id"], "anthropic")
        self.assertEqual(provider["models"], [])

    def test_unreachable_runtime_yields_an_empty_inventory(self) -> None:
        self.runtime.status.return_value = {
            "healthy": True,
            "base_url": "http://127.0.0.1:19192",
        }
        client = Mock()
        client.get.side_effect = KuraAgentError("connection refused")
        with patch("loopforge_agent.application.KuraClient", return_value=client):
            result = self.agent.providers()

        self.assertEqual(result["providers"], [])
        self.assertIn("connection refused", result["reason"])

    def test_skips_malformed_entries(self) -> None:
        self.runtime.status.return_value = {
            "healthy": True,
            "base_url": "http://127.0.0.1:19192",
        }
        client = Mock()
        client.get.side_effect = lambda path, query=None: (
            {"items": [{"title": "no id"}, "not-an-object", _kura_provider()]}
            if path == "/v1/providers"
            else {"items": []}
        )
        with patch("loopforge_agent.application.KuraClient", return_value=client):
            providers = self.agent.providers()["providers"]

        self.assertEqual([p["id"] for p in providers], ["anthropic"])

    def test_rejects_an_unrecognized_inventory_shape(self) -> None:
        self.runtime.status.return_value = {
            "healthy": True,
            "base_url": "http://127.0.0.1:19192",
        }
        client = Mock()
        client.get.return_value = {"providers": []}
        with patch("loopforge_agent.application.KuraClient", return_value=client):
            result = self.agent.providers()

        self.assertEqual(result["providers"], [])
        self.assertIn("unrecognized", result["reason"])


class ModelRoleProjectionTests(unittest.TestCase):
    """Role routing is a Kura runtime capability; Loopforge only projects it."""

    def setUp(self) -> None:
        self.runtime = Mock()
        self.runtime.status.return_value = {
            "healthy": True,
            "base_url": "http://127.0.0.1:19192",
        }
        self.agent = object.__new__(LoopforgeAgent)
        self.agent.runtime = self.runtime

    @staticmethod
    def _client(responses: dict) -> Mock:
        client = Mock()

        def _get(path: str, query: dict | None = None):
            if path in responses:
                value = responses[path]
                if isinstance(value, Exception):
                    raise value
                return value
            raise KuraAgentError(f"no route {path}")

        client.get.side_effect = _get
        return client

    def test_uses_embedded_models_instead_of_one_request_per_provider(self) -> None:
        client = self._client(
            {
                "/v1/providers": {
                    "items": [_kura_provider()],
                    "models": {
                        "anthropic": [
                            {
                                "providerId": "anthropic",
                                "modelId": "claude-sonnet",
                                "displayName": "Claude Sonnet",
                                "default": True,
                                "available": True,
                                "source": "builtin",
                                "chat": True,
                                "stream": True,
                                "coding": False,
                                "toolUse": True,
                            }
                        ]
                    },
                },
                "/v1/model-roles": {"items": []},
            }
        )
        with patch("loopforge_agent.application.KuraClient", return_value=client):
            result = self.agent.providers()

        (provider,) = result["providers"]
        self.assertEqual([m["id"] for m in provider["models"]], ["claude-sonnet"])
        # The point of the expansion: no per-provider model request.
        requested = [call.args[0] for call in client.get.call_args_list]
        self.assertNotIn("/v1/providers/anthropic/models", requested)
        # The real KuraClient rejects a path containing "?", so the expansion
        # must travel as a query argument rather than inside the path.
        listing_call = next(c for c in client.get.call_args_list if c.args[0] == "/v1/providers")
        self.assertNotIn("?", listing_call.args[0])
        self.assertEqual(listing_call.args[1], {"include": "models"})

    def test_falls_back_to_per_provider_models_on_an_older_runtime(self) -> None:
        # An older daemon ignores `include` and omits the key entirely.
        client = self._client(
            {
                "/v1/providers": {"items": [_kura_provider()]},
                "/v1/providers/anthropic/models": {"items": []},
                "/v1/model-roles": {"items": []},
            }
        )
        with patch("loopforge_agent.application.KuraClient", return_value=client):
            result = self.agent.providers()

        requested = [call.args[0] for call in client.get.call_args_list]
        self.assertIn("/v1/providers/anthropic/models", requested)
        self.assertEqual(result["providers"][0]["models"], [])

    def test_projects_roles_including_unrouted_ones(self) -> None:
        client = self._client(
            {
                "/v1/providers": {"items": [], "models": {}},
                "/v1/model-roles": {
                    "items": [
                        {
                            "role": "primary",
                            "providerId": "anthropic",
                            "model": "claude-sonnet",
                            "routed": True,
                            "source": "config",
                        },
                        {
                            "role": "video",
                            "providerId": "",
                            "model": "",
                            "routed": False,
                            "source": "unrouted",
                        },
                    ]
                },
            }
        )
        with patch("loopforge_agent.application.KuraClient", return_value=client):
            roles = self.agent.providers()["roles"]

        # An unrouted role must be reported, not filtered out: the UI has to
        # show that the capability is unavailable.
        self.assertEqual([r["role"] for r in roles], ["primary", "video"])
        self.assertFalse(roles[1]["routed"])

    def test_omits_roles_when_the_runtime_has_no_role_endpoint(self) -> None:
        """Absent roles and an empty role list mean different things."""
        client = self._client({"/v1/providers": {"items": [], "models": {}}})
        with patch("loopforge_agent.application.KuraClient", return_value=client):
            result = self.agent.providers()

        self.assertNotIn("roles", result)


class ProviderContractTests(unittest.TestCase):
    """Guards the cross-repository boundary: the projection must not grow a
    field that `loopforge-provider-v1` does not declare. This is the check that
    catches Loopforge quietly inventing provider state Kura does not own."""

    @staticmethod
    def _schema() -> dict:
        root = Path(__file__).resolve().parents[2]
        path = root / "contracts" / "loopforge-provider-v1.schema.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def _projected_provider(self) -> dict:
        runtime = Mock()
        runtime.status.return_value = {
            "healthy": True,
            "base_url": "http://127.0.0.1:19192",
        }
        agent = object.__new__(LoopforgeAgent)
        agent.runtime = runtime
        client = Mock()
        client.get.side_effect = lambda path, query=None: (
            {"items": [_kura_provider(accountLabel="kai@studio.dev", plan="Max")]}
            if path == "/v1/providers"
            else {
                "items": [
                    {
                        "providerId": "anthropic",
                        "modelId": "claude-sonnet",
                        "displayName": "Claude Sonnet",
                        "default": True,
                        "available": True,
                        "source": "builtin",
                        "chat": True,
                        "stream": False,
                        "coding": True,
                        "toolUse": True,
                    }
                ]
            }
        )
        with patch("loopforge_agent.application.KuraClient", return_value=client):
            return agent.providers()

    def test_envelope_matches_the_contract(self) -> None:
        schema = self._schema()
        result = self._projected_provider()
        allowed = set(schema["properties"])
        self.assertLessEqual(set(result), allowed)
        for field in schema["required"]:
            self.assertIn(field, result)
        self.assertEqual(
            result["schema_version"], schema["properties"]["schema_version"]["const"]
        )

    def test_provider_and_model_fields_are_declared(self) -> None:
        schema = self._schema()
        provider_schema = schema["$defs"]["provider"]
        model_schema = schema["$defs"]["model"]
        provider = self._projected_provider()["providers"][0]

        self.assertLessEqual(set(provider), set(provider_schema["properties"]))
        for field in provider_schema["required"]:
            self.assertIn(field, provider)

        model = provider["models"][0]
        self.assertLessEqual(set(model), set(model_schema["properties"]))
        for field in model_schema["required"]:
            self.assertIn(field, model)

    def test_model_capabilities_stay_within_the_declared_enum(self) -> None:
        allowed = set(
            self._schema()["$defs"]["model"]["properties"]["capabilities"]["items"]["enum"]
        )
        model = self._projected_provider()["providers"][0]["models"][0]
        self.assertLessEqual(set(model["capabilities"]), allowed)
        # `stream` was false upstream, so it must not be claimed.
        self.assertNotIn("stream", model["capabilities"])

    def test_health_stays_within_the_declared_enum(self) -> None:
        allowed = set(self._schema()["$defs"]["provider"]["properties"]["health"]["enum"])
        provider = self._projected_provider()["providers"][0]
        self.assertIn(provider["health"], allowed)


if __name__ == "__main__":
    unittest.main()
