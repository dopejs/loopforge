"""Probing an endpoint for its model list.

Run against a local HTTP server rather than a mock: the point of this code is
what a real endpoint does -- a 401 for a wrong key, a 404 for a base URL
missing its version segment, HTML where JSON was expected -- and a stub would
only confirm the shape I already assumed.
"""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from loopforge_agent.application import LoopforgeAgent, LoopforgeAgentError


class ProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = object.__new__(LoopforgeAgent)

    def _serve(self, status: int, body: bytes, expect_key: str | None = None) -> str:
        """A stand-in endpoint. Returns its base URL."""

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: object) -> None:
                return

            def do_GET(self) -> None:
                # Exact, not a suffix: `/models` without the version segment is
                # the mistake one of these cases is about, and endswith would
                # have served it happily.
                if self.path != "/v1/models":
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if expect_key is not None:
                    supplied = self.headers.get("Authorization", "")
                    if supplied != f"Bearer {expect_key}":
                        payload = b'{"error":{"message":"invalid api key"}}'
                        self.send_response(401)
                        self.send_header("Content-Length", str(len(payload)))
                        self.end_headers()
                        self.wfile.write(payload)
                        return
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}/v1"

    def test_an_openai_style_listing_becomes_model_ids(self) -> None:
        catalogue = json.dumps(
            {
                "object": "list",
                "data": [
                    {"id": "deepseek-chat", "object": "model"},
                    {"id": "deepseek-reasoner", "object": "model"},
                ],
            }
        ).encode()
        base = self._serve(200, catalogue)

        result = self.agent.probe_provider(base, "sk-1")

        self.assertTrue(result["reachable"])
        self.assertEqual(result["models"], ["deepseek-chat", "deepseek-reasoner"])

    def test_the_key_is_sent_and_a_wrong_one_is_reported_as_such(self) -> None:
        """The status is what tells a user which field is wrong, so it survives
        rather than being flattened into "could not connect"."""
        base = self._serve(200, b'{"data":[]}', expect_key="sk-right")

        result = self.agent.probe_provider(base, "sk-wrong")

        self.assertFalse(result["reachable"])
        self.assertEqual(result["status"], 401)

    def test_a_base_url_missing_its_version_segment_is_reported(self) -> None:
        """The commonest mistake: pasting a host without /v1."""
        base = self._serve(200, b'{"data":[]}')
        wrong = base.rsplit("/v1", 1)[0]

        result = self.agent.probe_provider(wrong, "sk-1")

        self.assertFalse(result["reachable"])
        self.assertEqual(result["status"], 404)

    def test_html_where_json_was_expected_is_not_a_crash(self) -> None:
        base = self._serve(200, b"<!doctype html><title>Login</title>")

        result = self.agent.probe_provider(base, "sk-1")

        self.assertFalse(result["reachable"])
        self.assertIn("model list", result["error"])

    def test_an_unreachable_host_reports_why(self) -> None:
        result = self.agent.probe_provider("http://127.0.0.1:1/v1", "sk-1")
        self.assertFalse(result["reachable"])
        self.assertTrue(result["error"])

    def test_duplicate_ids_are_collapsed_and_ordered(self) -> None:
        """Same endpoint, same list twice -- vendors do not promise an order."""
        catalogue = json.dumps(
            {"data": [{"id": "b"}, {"id": "a"}, {"id": "b"}]}
        ).encode()
        base = self._serve(200, catalogue)

        self.assertEqual(self.agent.probe_provider(base, "k")["models"], ["a", "b"])

    def test_a_bare_array_listing_is_accepted(self) -> None:
        """Not every compatible endpoint wraps the list in `data`."""
        base = self._serve(200, json.dumps([{"id": "solo"}]).encode())
        self.assertEqual(self.agent.probe_provider(base, "k")["models"], ["solo"])

    def test_a_missing_or_non_http_url_is_refused(self) -> None:
        for value in ("", "   ", "ftp://x.test/v1", "file:///etc/passwd", "not-a-url"):
            with self.subTest(value=value), self.assertRaises(LoopforgeAgentError) as caught:
                self.agent.probe_provider(value, "k")
            self.assertEqual(caught.exception.code, "PROBE_URL_INVALID")

    def test_the_model_count_is_bounded(self) -> None:
        """A wrong endpoint should not be able to fill the list with whatever
        it happens to return."""
        catalogue = json.dumps({"data": [{"id": f"m{n}"} for n in range(600)]}).encode()
        base = self._serve(200, catalogue)

        self.assertEqual(len(self.agent.probe_provider(base, "k")["models"]), 500)


if __name__ == "__main__":
    unittest.main()
