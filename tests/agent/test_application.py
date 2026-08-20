from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

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


if __name__ == "__main__":
    unittest.main()
