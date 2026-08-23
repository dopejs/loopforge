"""Reading subscription limits out of the CLIs' own session records.

The shapes here are taken from real Codex rollouts rather than invented: the
empty limit events, the seven-day window arriving in the `primary` slot, and a
recent file whose newest event is older than an older file's are all things
the format actually does, and each one produced a wrong answer first.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from unittest import mock

from loopforge.oauth.usage import UsageUnavailable
from loopforge.userstore import UserStore
from loopforge.accountusage import (
    TAIL_BYTES,
    _tail_lines,
    account_usage,
    claude_usage,
    codex_usage,
)


def limits(
    *,
    primary: dict[str, object] | None = None,
    secondary: dict[str, object] | None = None,
    plan: str | None = "prolite",
    limit_id: str = "codex",
    credits: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "limit_id": limit_id,
        "limit_name": None,
        "primary": primary,
        "secondary": secondary,
        "credits": credits,
        "plan_type": plan,
    }


def window(minutes: int, used: float, resets_at: int = 1787801631) -> dict[str, object]:
    return {"used_percent": used, "window_minutes": minutes, "resets_at": resets_at}


def stamp_epoch(stamp: str) -> float:
    """A rollout timestamp as a file mtime.

    Kept consistent with the events a fixture contains: a rollout is appended
    to, so its last write is never earlier than the last event in it, and a
    fixture that says otherwise tests a state the format cannot reach.
    """
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()


def event(stamp: str, payload: dict[str, object]) -> str:
    return json.dumps(
        {
            "timestamp": stamp,
            "type": "event_msg",
            "payload": {"type": "token_count", "info": {}, "rate_limits": payload},
        }
    )


class CodexUsageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        self.sessions = self.home / ".codex" / "sessions" / "2026" / "08"
        self.sessions.mkdir(parents=True)
        self.addCleanup(self.temporary.cleanup)

    def rollout(self, name: str, lines: list[str], modified: float | None = None) -> Path:
        path = self.sessions / f"rollout-{name}.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if modified is not None:
            os.utime(path, (modified, modified))
        return path

    def test_windows_are_read_from_the_newest_populated_event(self) -> None:
        self.rollout(
            "a",
            [
                event("2026-08-22T08:00:00.000Z", limits(primary=window(300, 6.0))),
                event("2026-08-22T10:45:34.000Z", limits(primary=window(300, 41.0))),
            ],
        )

        usage = codex_usage(self.home)

        self.assertTrue(usage.available)
        self.assertEqual(usage.plan, "prolite")
        self.assertEqual([w.used_percent for w in usage.windows], [41.0])
        self.assertEqual(usage.observed_at, "2026-08-22T10:45:34Z")

    def test_an_empty_newest_event_does_not_hide_the_figure_above_it(self) -> None:
        """More than half of the real events carry no window at all.

        Taking the latest event rather than the latest populated one reports
        "no data" while the answer sits a few lines earlier in the same file.
        """
        self.rollout(
            "a",
            [
                event("2026-08-22T08:00:00.000Z", limits(primary=window(300, 6.0))),
                event("2026-08-23T02:00:00.000Z", limits()),
                event("2026-08-23T03:00:00.000Z", limits()),
            ],
        )

        usage = codex_usage(self.home)

        self.assertTrue(usage.available)
        self.assertEqual([w.used_percent for w in usage.windows], [6.0])

    def test_the_seven_day_window_is_labelled_by_duration_not_by_slot(self) -> None:
        """Real rollouts put the weekly window in `primary` in some sessions
        and in `secondary` in others, so the slot name cannot name it."""
        self.rollout("a", [event("2026-08-22T08:00:00.000Z", limits(primary=window(10080, 75.0)))])

        usage = codex_usage(self.home)

        self.assertEqual([(w.label, w.used_percent) for w in usage.windows], [("7d", 75.0)])

    def test_both_windows_are_ordered_shortest_first(self) -> None:
        self.rollout(
            "a",
            [
                event(
                    "2026-08-22T08:00:00.000Z",
                    limits(primary=window(10080, 3.0), secondary=window(300, 6.0)),
                )
            ],
        )

        usage = codex_usage(self.home)

        self.assertEqual([w.label for w in usage.windows], ["5h", "7d"])

    def test_a_reset_time_is_reported_as_an_instant(self) -> None:
        self.rollout(
            "a",
            [event("2026-08-22T08:00:00.000Z", limits(primary=window(300, 6.0, 1787801631)))],
        )

        self.assertEqual(codex_usage(self.home).windows[0].resets_at, "2026-08-27T03:33:51Z")

    def test_a_recent_file_does_not_outrank_a_newer_event_elsewhere(self) -> None:
        """File order is not event order.

        A long session keeps being written to -- mostly with events carrying no
        limits at all -- so its file can be the most recently touched while the
        last figure it recorded is days old. Ranking by file and stopping at
        the first hit reports that stale figure.
        """
        self.rollout(
            "long-session-touched-recently",
            [
                event("2026-08-20T08:00:00.000Z", limits(primary=window(300, 9.0))),
                event("2026-08-23T09:00:00.000Z", limits()),
            ],
            modified=stamp_epoch("2026-08-23T09:00:00.000Z"),
        )
        self.rollout(
            "older-file-newer-figure",
            [event("2026-08-22T08:00:00.000Z", limits(primary=window(300, 88.0)))],
            modified=stamp_epoch("2026-08-22T08:00:00.000Z"),
        )

        usage = codex_usage(self.home)

        self.assertEqual([w.used_percent for w in usage.windows], [88.0])

    def test_a_file_larger_than_the_tail_budget_is_still_read(self) -> None:
        """Rollouts reach hundreds of megabytes, so only the end is read."""
        filler = json.dumps({"timestamp": "2026-08-22T00:00:00.000Z", "payload": {"x": "y" * 400}})
        padding = [filler] * ((TAIL_BYTES // len(filler)) + 40)
        self.rollout(
            "huge",
            [*padding, event("2026-08-22T09:00:00.000Z", limits(primary=window(300, 12.0)))],
        )

        usage = codex_usage(self.home)

        self.assertTrue(usage.available)
        self.assertEqual([w.used_percent for w in usage.windows], [12.0])

    def test_only_the_end_of_a_file_is_read(self) -> None:
        """The bound is the point, not an optimisation.

        A single rollout reaches hundreds of megabytes and a developer's
        directory runs to gigabytes, so a reader that walks whole files turns
        opening a usage panel into a disk-bound operation. Nothing about the
        reported figures would change, which is why it is asserted here.
        """
        path = self.rollout("a", [f"line-{index:04d}" + "x" * 96 for index in range(400)])

        tail = _tail_lines(path, limit=1024)

        self.assertLess(len(tail), 20)
        self.assertTrue(tail[-1].startswith("line-0399"))

    def test_a_partial_first_line_is_discarded(self) -> None:
        """Reading from an offset lands mid-line, and half a record is not a
        record -- it must never reach the parser as one."""
        path = self.rollout("a", [f"line-{index:04d}" + "x" * 96 for index in range(400)])

        tail = _tail_lines(path, limit=1024)

        self.assertTrue(all(line.startswith("line-") for line in tail))

    def test_credits_are_passed_through_as_the_vendor_formatted_them(self) -> None:
        self.rollout(
            "a",
            [
                event(
                    "2026-08-22T08:00:00.000Z",
                    limits(
                        primary=window(300, 6.0),
                        credits={"has_credits": True, "unlimited": False, "balance": "12.50"},
                    ),
                )
            ],
        )

        usage = codex_usage(self.home)

        self.assertEqual(usage.credit_balance, "12.50")
        self.assertFalse(usage.credits_unlimited)

    def test_a_damaged_line_does_not_lose_the_rest_of_the_file(self) -> None:
        self.rollout(
            "a",
            [
                '{"timestamp": "2026-08-22T07:00:00.000Z", "payload": {"rate_limits": tru',
                event("2026-08-22T08:00:00.000Z", limits(primary=window(300, 6.0))),
            ],
        )

        self.assertTrue(codex_usage(self.home).available)

    def test_no_sessions_at_all_says_so_rather_than_reporting_zero(self) -> None:
        """Nothing recorded is not the same as nothing used, and a usage panel
        showing 0% for an untouched account would be a lie."""
        usage = codex_usage(self.home / "elsewhere")

        self.assertFalse(usage.available)
        self.assertEqual(usage.windows, ())
        self.assertIn("No Codex sessions", usage.reason)

    def test_sessions_that_recorded_no_limits_say_so(self) -> None:
        self.rollout("a", [event("2026-08-23T02:00:00.000Z", limits())])

        usage = codex_usage(self.home)

        self.assertFalse(usage.available)
        self.assertIn("no limit information", usage.reason)


class ClaudeUsageTests(unittest.TestCase):
    def test_the_balance_points_at_signing_in_rather_than_at_a_dead_end(self) -> None:
        """Claude writes no window to disk, so nothing local can be scavenged.

        The figure is behind an authenticated request, which signing the
        account in provides -- so the reason names the action that fixes it
        rather than describing a limitation.
        """
        usage = claude_usage(Path("/nonexistent"))

        self.assertFalse(usage.available)
        self.assertEqual(usage.windows, ())
        self.assertIn("Sign the account in", usage.reason)


class VendorRouteTests(unittest.TestCase):
    """Which source answers, once an account has been signed in."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.store = UserStore(self.home / "store")

    def test_a_signed_in_account_is_asked_directly(self) -> None:
        """The whole point of holding a grant: the answer is from the vendor
        now, not from whatever a CLI last wrote down."""
        self.store.save_oauth_grant(
            {"provider_id": "anthropic", "access_token": "at", "refresh_token": "rt"}
        )
        fetched = {
            "observed_at": "2026-08-23T10:00:00Z",
            "windows": [
                {"label": "5h", "window_minutes": 300, "used_percent": 42.0, "resets_at": ""}
            ],
        }
        with mock.patch.dict(
            "loopforge.oauth.usage.FETCHERS", {"anthropic": lambda *_: fetched}
        ):
            reported = {item.provider_id: item for item in account_usage(self.home, self.store)}

        claude = reported["claude_managed"]
        self.assertTrue(claude.available)
        self.assertEqual(claude.source, "vendor")
        self.assertEqual([w.used_percent for w in claude.windows], [42.0])

    def test_an_account_never_signed_in_falls_back_to_the_local_reading(self) -> None:
        reported = {item.provider_id: item for item in account_usage(self.home, self.store)}

        claude = reported["claude_managed"]
        self.assertEqual(claude.source, "local")
        self.assertIn("Sign the account in", claude.reason)

    def test_an_account_beyond_the_two_managed_ones_is_reported_too(self) -> None:
        """A user who signs Kimi in here has a readable balance. Listing only
        the accounts the runtime reaches through a CLI would leave it missing
        from the one surface that exists to show balances."""
        self.store.save_oauth_grant(
            {"provider_id": "kimi", "access_token": "at", "refresh_token": "rt"}
        )
        fetched = {
            "observed_at": "2026-08-23T10:00:00Z",
            "windows": [
                {"label": "5h", "window_minutes": 300, "used_percent": 8.0, "resets_at": ""}
            ],
        }

        with mock.patch.dict(
            "loopforge.oauth.usage.FETCHERS", {"kimi": lambda *_: fetched}
        ):
            reported = {item.provider_id: item for item in account_usage(self.home, self.store)}

        self.assertIn("kimi", reported)
        self.assertTrue(reported["kimi"].available)
        # Named by the vendor, since no endpoint preset covers it.
        self.assertEqual(reported["kimi"].display_name, "Kimi")

    def test_an_account_with_no_fetcher_is_not_invented(self) -> None:
        """Signing in does not by itself make a balance readable, and showing
        a row that can never be filled is worse than not showing one."""
        self.store.save_oauth_grant(
            {"provider_id": "gitlab_duo", "access_token": "at", "refresh_token": "rt"}
        )

        reported = [item.provider_id for item in account_usage(self.home, self.store)]

        self.assertNotIn("gitlab_duo", reported)

    def test_a_vendor_that_cannot_answer_does_not_take_the_panel_down(self) -> None:
        """A moved endpoint or a dead grant degrades to the local reading
        rather than to an error where a figure used to be."""
        self.store.save_oauth_grant({"provider_id": "anthropic", "access_token": "at"})

        def refuse(*_: object) -> dict[str, object]:
            raise UsageUnavailable("HTTP 401")

        with mock.patch.dict("loopforge.oauth.usage.FETCHERS", {"anthropic": refuse}):
            reported = {item.provider_id: item for item in account_usage(self.home, self.store)}

        self.assertEqual(reported["claude_managed"].source, "local")


class AccountUsageTests(unittest.TestCase):
    def test_every_subscription_account_is_accounted_for(self) -> None:
        """An account with no readable figure still appears, carrying its
        reason: silently omitting it would read as "no such account"."""
        with tempfile.TemporaryDirectory() as home:
            reported = account_usage(Path(home))

        self.assertEqual(
            [item.provider_id for item in reported], ["codex_managed", "claude_managed"]
        )
        self.assertTrue(all(item.reason for item in reported if not item.available))


if __name__ == "__main__":
    unittest.main()
