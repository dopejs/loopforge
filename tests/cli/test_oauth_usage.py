"""Asking the vendor for a subscription's remaining allowance.

The payloads here are the shapes the account endpoint actually returns,
including the two that cost omp real bugs: the per-model weekly buckets that
have been permanently null since mid-2026, and the `is_active` flag that marks
only the currently binding limit -- so filtering on it hides utilization that
is genuinely being consumed.
"""

from __future__ import annotations

import json
import threading
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler

from tests.support.httpstub import serve

from loopforge.oauth.registry import ANTHROPIC, KIMI, OPENAI_CODEX, XAI, ZAI
from loopforge.oauth.usage import (
    UsageUnavailable,
    anthropic_usage,
    codex_usage,
    kimi_usage,
    xai_usage,
    zai_usage,
)


class AnthropicUsageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.status = 200
        self.payload: object = {}
        self.seen: dict[str, str] = {}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: object) -> None:
                return

            def do_GET(self) -> None:
                outer.seen["path"] = self.path
                outer.seen["auth"] = self.headers.get("Authorization", "")
                outer.seen["beta"] = self.headers.get("anthropic-beta", "")
                outer.seen["agent"] = self.headers.get("User-Agent", "")
                body = json.dumps(outer.payload).encode()
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server, base = serve(Handler)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.provider = replace(
            ANTHROPIC,
            usage_url=f"http://127.0.0.1:{self.server.server_port}/api/oauth/usage",
        )

    def test_the_account_windows_are_read(self) -> None:
        self.payload = {
            "five_hour": {"utilization": 12.5, "resets_at": "2026-08-23T16:00:00Z"},
            "seven_day": {"utilization": 68.0, "resets_at": "2026-08-27T09:00:00Z"},
        }

        usage = anthropic_usage(self.provider, "at-1")

        self.assertTrue(usage["available"])
        self.assertEqual(
            [(w["label"], w["used_percent"]) for w in usage["windows"]],
            [("5h", 12.5), ("7d", 68.0)],
        )
        self.assertEqual(usage["windows"][0]["resets_at"], "2026-08-23T16:00:00Z")
        # The point of holding a grant: the answer is from now, not from disk.
        self.assertEqual(usage["source"], "vendor")

    def test_the_grant_is_presented_as_the_client_it_was_minted_as(self) -> None:
        self.payload = {"five_hour": {"utilization": 1.0}}

        anthropic_usage(self.provider, "at-secret")

        self.assertEqual(self.seen["auth"], "Bearer at-secret")
        self.assertIn("oauth-2025-04-20", self.seen["beta"])
        self.assertIn("claude-cli/", self.seen["agent"])

    def test_null_per_model_buckets_are_not_mistaken_for_zero(self) -> None:
        """These have been permanently null since mid-2026; reading them as 0%
        would draw an empty bar for a limit that simply is not reported here."""
        self.payload = {
            "seven_day": {"utilization": 40.0},
            "seven_day_opus": None,
            "seven_day_sonnet": None,
        }

        usage = anthropic_usage(self.provider, "at")

        self.assertEqual([w["label"] for w in usage["windows"]], ["7d"])

    def test_a_bucket_present_but_empty_is_not_reported_as_zero(self) -> None:
        """The vendor sends the key with nothing in it while a window is not
        being tracked. `{}` means "not reported", and 0% means "none used" --
        drawing the first as the second invents an allowance."""
        self.payload = {"five_hour": {}, "seven_day": {"utilization": 20.0}}

        usage = anthropic_usage(self.provider, "at")

        self.assertEqual([w["label"] for w in usage["windows"]], ["7d"])

    def test_a_scoped_limit_marked_inactive_is_still_reported(self) -> None:
        """`is_active` ranks severity rather than stating existence: an account
        pinned at one cap reports its other real limits as inactive. Filtering
        on it hides allowance that is genuinely being consumed."""
        self.payload = {
            "five_hour": {"utilization": 3.0},
            "limits": [
                {
                    "kind": "weekly_scoped",
                    "percent": 77.0,
                    "resets_at": "2026-08-30T00:00:00Z",
                    "is_active": False,
                    "scope": {"model": {"display_name": "Opus"}},
                }
            ],
        }

        usage = anthropic_usage(self.provider, "at")

        scoped = [w for w in usage["windows"] if w["label"] == "Opus"]
        self.assertEqual(len(scoped), 1)
        self.assertEqual(scoped[0]["used_percent"], 77.0)

    def test_a_scoped_limit_without_a_model_name_falls_back_to_its_kind(self) -> None:
        self.payload = {"limits": [{"kind": "weekly_shared", "percent": 5.0}]}

        usage = anthropic_usage(self.provider, "at")

        self.assertEqual(usage["windows"][0]["label"], "weekly_shared")

    def test_an_empty_limits_entry_is_skipped_rather_than_drawn_at_zero(self) -> None:
        self.payload = {
            "seven_day": {"utilization": 10.0},
            "limits": [{"kind": "weekly_scoped", "percent": None, "resets_at": None}],
        }

        usage = anthropic_usage(self.provider, "at")

        self.assertEqual(len(usage["windows"]), 1)

    def test_a_stale_grant_is_reported_with_its_status(self) -> None:
        """401 is the one the caller can fix, by refreshing."""
        self.status = 401
        self.payload = {"error": {"message": "invalid bearer token"}}

        with self.assertRaises(UsageUnavailable) as caught:
            anthropic_usage(self.provider, "at-expired")

        self.assertIn("401", str(caught.exception))

    def test_a_payload_with_no_limits_at_all_is_not_reported_as_zero(self) -> None:
        """A vendor that has moved its schema must degrade to "no figure", not
        to a confident 0%."""
        self.payload = {"something_else": True}

        with self.assertRaises(UsageUnavailable):
            anthropic_usage(self.provider, "at")

    def test_html_where_json_was_expected_is_not_a_crash(self) -> None:
        self.payload = "<!doctype html>"
        with self.assertRaises(UsageUnavailable):
            anthropic_usage(replace(self.provider, usage_url=self.provider.usage_url), "at")

    def test_extra_usage_credits_are_summarised(self) -> None:
        self.payload = {
            "five_hour": {"utilization": 1.0},
            "extra_usage": {
                "is_enabled": True,
                "used_credits": 4.5,
                "monthly_limit": 20,
                "currency": "USD",
            },
        }

        usage = anthropic_usage(self.provider, "at")

        self.assertEqual(usage["credit_balance"], "4.5 / 20 USD")


if __name__ == "__main__":
    unittest.main()


class CodexUsageTests(unittest.TestCase):
    """The same figures the CLI writes to its rollouts, asked for directly."""

    def setUp(self) -> None:
        self.payload: object = {}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: object) -> None:
                return

            def do_GET(self) -> None:
                body = json.dumps(outer.payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server, base = serve(Handler)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.provider = replace(OPENAI_CODEX, usage_url=f"{base}/backend-api/wham/usage")

    def test_windows_stated_in_seconds_become_named_durations(self) -> None:
        """The account endpoint gives a window length in seconds where the
        rollouts give minutes, so the same limit has to come out named the
        same way from either route."""
        self.payload = {
            "rate_limit": {
                "primary_window": {"used_percent": 6.0, "limit_window_seconds": 18000},
                "secondary_window": {"used_percent": 61.0, "limit_window_seconds": 604800},
            },
            "plan_type": "plus",
        }

        usage = codex_usage(self.provider, "at")

        self.assertEqual(
            [(w["label"], w["window_minutes"], w["used_percent"]) for w in usage["windows"]],
            [("5h", 300, 6.0), ("7d", 10080, 61.0)],
        )
        self.assertEqual(usage["plan"], "plus")

    def test_windows_come_out_shortest_first_whichever_slot_carried_them(self) -> None:
        self.payload = {
            "rate_limit": {
                "primary_window": {"used_percent": 61.0, "limit_window_seconds": 604800},
                "secondary_window": {"used_percent": 6.0, "limit_window_seconds": 18000},
            }
        }

        usage = codex_usage(self.provider, "at")

        self.assertEqual([w["label"] for w in usage["windows"]], ["5h", "7d"])

    def test_an_absolute_reset_is_read_as_an_instant(self) -> None:
        self.payload = {
            "rate_limit": {
                "primary_window": {
                    "used_percent": 1.0,
                    "limit_window_seconds": 18000,
                    "reset_at": 1787801631,
                }
            }
        }

        usage = codex_usage(self.provider, "at")

        self.assertEqual(usage["windows"][0]["resets_at"], "2026-08-27T03:33:51Z")

    def test_a_relative_reset_is_turned_into_one(self) -> None:
        """Some payloads give only an offset, and a countdown that is not
        anchored cannot be re-read later."""
        self.payload = {
            "rate_limit": {
                "primary_window": {
                    "used_percent": 1.0,
                    "limit_window_seconds": 18000,
                    "reset_after_seconds": 3600,
                }
            }
        }

        usage = codex_usage(self.provider, "at")

        self.assertTrue(usage["windows"][0]["resets_at"].endswith("Z"))

    def test_a_model_specific_allowance_is_named_after_it(self) -> None:
        """These arrive as separate buckets; merging them into the plan's own
        windows would describe an allowance that does not exist."""
        self.payload = {
            "rate_limit": {"primary_window": {"used_percent": 2.0, "limit_window_seconds": 18000}},
            "additional_rate_limits": [
                {
                    "limit_name": "Spark",
                    "rate_limit": {
                        "primary_window": {"used_percent": 9.0, "limit_window_seconds": 604800}
                    },
                }
            ],
        }

        usage = codex_usage(self.provider, "at")

        self.assertIn("Spark 7d", [w["label"] for w in usage["windows"]])

    def test_a_payload_with_no_windows_is_not_reported_as_zero(self) -> None:
        self.payload = {"rate_limit": None}
        with self.assertRaises(UsageUnavailable):
            codex_usage(self.provider, "at")


class JsonEndpoint(unittest.TestCase):
    """A stand-in account endpoint returning whatever the test sets."""

    def setUp(self) -> None:
        self.payload: object = {}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: object) -> None:
                return

            def do_GET(self) -> None:
                body = json.dumps(outer.payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server, self.base = serve(Handler)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def at(self, provider):
        return replace(provider, usage_url=f"{self.base}/usage")


class KimiUsageTests(JsonEndpoint):
    def test_a_count_is_turned_into_a_fraction(self) -> None:
        """The vendor reports "1200 of 2000"; a bar needs a proportion, and
        drawing the raw count would read as 1200%."""
        self.payload = {
            "limits": [
                {
                    "used": 1200,
                    "limit": 2000,
                    "window": {"duration": 5, "timeUnit": "HOURS"},
                    "resetsAt": 1787801631,
                }
            ]
        }

        usage = kimi_usage(self.at(KIMI), "at")

        self.assertEqual(usage["windows"][0]["used_percent"], 60.0)
        self.assertEqual(usage["windows"][0]["label"], "5h")
        self.assertEqual(usage["windows"][0]["resets_at"], "2026-08-27T03:33:51Z")

    def test_a_remaining_count_is_inverted(self) -> None:
        self.payload = {"limits": [{"remaining": 500, "limit": 2000}]}

        usage = kimi_usage(self.at(KIMI), "at")

        self.assertEqual(usage["windows"][0]["used_percent"], 75.0)

    def test_an_entry_with_no_usable_figure_is_skipped(self) -> None:
        self.payload = {"limits": [{"limit": 0}, {"used": 10, "limit": 100}]}

        usage = kimi_usage(self.at(KIMI), "at")

        self.assertEqual(len(usage["windows"]), 1)

    def test_nothing_reportable_is_not_reported_as_zero(self) -> None:
        self.payload = {"limits": []}
        with self.assertRaises(UsageUnavailable):
            kimi_usage(self.at(KIMI), "at")


class ZaiUsageTests(JsonEndpoint):
    def test_the_stated_percentage_is_used_when_present(self) -> None:
        self.payload = {
            "data": {
                "limits": [
                    {"type": "daily", "percentage": 42.0, "nextResetTime": 1787801631000}
                ]
            }
        }

        usage = zai_usage(self.at(ZAI), "at")

        self.assertEqual(usage["windows"][0]["used_percent"], 42.0)
        # Milliseconds, not seconds -- read as seconds this lands in the year
        # 58000 and renders as a limit that never resets.
        self.assertEqual(usage["windows"][0]["resets_at"], "2026-08-27T03:33:51Z")

    def test_a_count_is_used_when_no_percentage_is_given(self) -> None:
        self.payload = {"data": {"limits": [{"type": "monthly", "usage": 25, "number": 200}]}}

        usage = zai_usage(self.at(ZAI), "at")

        self.assertEqual(usage["windows"][0]["used_percent"], 12.5)

    def test_a_failed_envelope_is_not_read_as_no_usage(self) -> None:
        self.payload = {"success": False, "msg": "unauthorized"}
        with self.assertRaises(UsageUnavailable):
            zai_usage(self.at(ZAI), "at")


class XaiUsageTests(JsonEndpoint):
    def test_a_plan_percentage_is_reported(self) -> None:
        self.payload = {"usagePercent": 31.0, "resetsAt": 1787801631}

        usage = xai_usage(self.at(XAI), "at")

        self.assertEqual(usage["windows"][0]["used_percent"], 31.0)

    def test_credits_become_both_a_balance_and_a_bar(self) -> None:
        """With no percentage on offer, the spend against the cap is the only
        thing that can be drawn."""
        self.payload = {"used": 12, "monthlyLimit": 60}

        usage = xai_usage(self.at(XAI), "at")

        self.assertEqual(usage["credit_balance"], "12 / 60")
        self.assertEqual(usage["windows"][0]["used_percent"], 20.0)

    def test_an_empty_billing_payload_is_not_reported_as_zero(self) -> None:
        self.payload = {}
        with self.assertRaises(UsageUnavailable):
            xai_usage(self.at(XAI), "at")
