from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from typing import Any

from loopforge_agent.server import AgentHTTPServer


class FakeAgent:
    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": "loopforge-agent-manifest-v1",
            "skills": [{"name": "loopforge-router", "sha256": "a" * 64}],
        }

    def status(self) -> dict[str, Any]:
        return {"schema_version": "loopforge-agent-status-v1", "ready": True}

    def start(self) -> dict[str, Any]:
        return self.status()

    def stop(self) -> dict[str, Any]:
        return {"schema_version": "loopforge-agent-status-v1", "ready": False}

    def query(self, query: str, thread_id: str | None = None) -> dict[str, Any]:
        return {
            "schema_version": "loopforge-agent-response-v1",
            "reply": query,
            "thread_id": thread_id,
        }


class AgentServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.token = "a" * 32
        self.server = AgentHTTPServer(
            ("127.0.0.1", 0),
            FakeAgent(),
            self.token,  # type: ignore[arg-type]
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(
        self, path: str, method: str = "GET", body: dict[str, Any] | None = None
    ) -> tuple[int, dict[str, Any]]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method=method,
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read())

    def test_health_is_available_without_exposing_agent_state(self) -> None:
        request = urllib.request.Request(f"{self.base_url}/healthz")
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["service"], "loopforge-agent")

    def test_status_requires_bearer_token(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(f"{self.base_url}/v1/status", timeout=2)
        self.assertEqual(raised.exception.code, 401)

    def test_query_uses_agent_contract(self) -> None:
        status, payload = self.request(
            "/v1/query", "POST", {"query": "inspect", "thread_id": "thread_1"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["schema_version"], "loopforge-agent-response-v1")
        self.assertEqual(payload["reply"], "inspect")


if __name__ == "__main__":
    unittest.main()
