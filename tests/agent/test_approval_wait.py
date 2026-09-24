"""The client must not give up before the runtime does.

A turn is allowed to stop and wait for a person: the model asks to run
`loopforge_init`, the runtime holds the call open, and somebody decides. The
Agent's HTTP timeout was 120 seconds and the runtime's approval wait is 180, so
the request died before anyone could plausibly have read the question.

On the streaming route -- the one the workbench uses -- that timeout is per
read, and an approval nobody answers within two minutes is indistinguishable
from a stalled generation. On the blocking route it kills the turn outright and
leaves the approval pending, so the next turn fails as well.

Two numbers in two languages in two repositories. A comment saying they agree
is a comment that will be wrong one day, so this reads the Rust.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from loopforge_agent.application import CHAT_TIMEOUT_SECONDS

#: Where the runtime states how long it will hold a tool call for a person.
AGENT_TOOL = (
    Path(__file__).resolve().parents[2]
    / "apps"
    / "workbench"
    / "vendor"
    / "kura"
    / "crates"
    / "domains"
    / "mcp"
    / "src"
    / "agent_tool.rs"
)


def approval_wait_seconds() -> int:
    """The runtime's own number, read from the runtime."""
    source = AGENT_TOOL.read_text(encoding="utf-8")
    match = re.search(
        r"const APPROVAL_WAIT:\s*Duration\s*=\s*Duration::from_secs\((\d+)\)", source
    )
    if not match:
        raise AssertionError(
            f"APPROVAL_WAIT is not where this test expects it in {AGENT_TOOL}; "
            "the constants can no longer be compared and the timeout may be short."
        )
    return int(match.group(1))


class TheClientOutlastsTheRuntime(unittest.TestCase):
    def test_the_runtime_still_states_how_long_it_waits(self) -> None:
        # If this stops being findable, every other assertion here is vacuous.
        self.assertGreater(approval_wait_seconds(), 0)

    def test_a_turn_is_given_longer_than_a_person_is(self) -> None:
        # The bug exactly: 120 against 180.
        self.assertGreater(
            CHAT_TIMEOUT_SECONDS,
            approval_wait_seconds(),
            "a turn that stops for an approval would be abandoned before the "
            "runtime stops waiting for one",
        )

    def test_with_room_for_the_turn_around_the_wait(self) -> None:
        # Not merely greater. A turn is the model thinking, then the approval,
        # then the model reading the result -- so a margin that only just
        # clears the wait would fail on the round either side of it.
        self.assertGreaterEqual(
            CHAT_TIMEOUT_SECONDS - approval_wait_seconds(),
            60,
            "the margin over the approval wait leaves nothing for the rounds "
            "either side of it",
        )


if __name__ == "__main__":
    unittest.main()
