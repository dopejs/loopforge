"""How much the agent may do without asking.

Three modes over three tiers. What matters is the middle one: being asked
before every build is how a person stops reading the questions, and someone who
stops reading them will approve a claim without looking.
"""

from __future__ import annotations

import unittest

from loopforge.mcp import TIER_CLAIM, TIER_EVIDENCE, TIER_READ, TOOLS
from loopforge.permissions import (
    DEFAULT_MODE,
    MODE_ALLOW_EDIT,
    MODE_ASK,
    MODE_AUTO,
    MODES,
    describe,
    exposure_for,
    normalize,
)


class PermissionModeTests(unittest.TestCase):
    def test_reading_is_never_worth_asking_about(self) -> None:
        """Under every mode, including the strictest. A question about a read
        is a question a person learns to click through."""
        for mode in MODES:
            with self.subTest(mode=mode):
                self.assertEqual(exposure_for(TIER_READ, mode), "allow")

    def test_ask_stops_at_everything_that_changes_the_project(self) -> None:
        self.assertEqual(exposure_for(TIER_EVIDENCE, MODE_ASK), "approval_required")
        self.assertEqual(exposure_for(TIER_CLAIM, MODE_ASK), "approval_required")

    def test_allow_edit_lets_work_happen_and_stops_at_a_claim(self) -> None:
        """The mode a person actually works in, and the distinction it turns
        on: doing the work is not asserting the work was good."""
        self.assertEqual(exposure_for(TIER_EVIDENCE, MODE_ALLOW_EDIT), "allow")
        self.assertEqual(exposure_for(TIER_CLAIM, MODE_ALLOW_EDIT), "approval_required")

    def test_auto_asks_nothing(self) -> None:
        for tier in (TIER_READ, TIER_EVIDENCE, TIER_CLAIM):
            with self.subTest(tier=tier):
                self.assertEqual(exposure_for(tier, MODE_AUTO), "allow")

    def test_a_tier_this_build_cannot_place_is_always_asked_about(self) -> None:
        """A command nobody has decided about is one to ask about, under every
        mode including `auto` -- which is the direction that fails safely."""
        for mode in MODES:
            with self.subTest(mode=mode):
                self.assertEqual(exposure_for("something-new", mode), "approval_required")

    def test_an_unrecognized_mode_narrows_rather_than_widens(self) -> None:
        """A mode from a store written by another build should reduce what the
        agent may do, not stop the daemon or open it up."""
        for stored in ("", None, "yolo", "ALLOW-EDIT"):
            with self.subTest(stored=stored):
                self.assertEqual(normalize(stored), DEFAULT_MODE)
        self.assertEqual(DEFAULT_MODE, MODE_ASK)

    def test_every_mode_says_what_it_means(self) -> None:
        """A person choosing has to be told what they are choosing, and the
        wording lives with the behaviour so the two cannot drift."""
        for mode in MODES:
            with self.subTest(mode=mode):
                summary = describe(mode)["summary"]
                self.assertTrue(summary.strip())
                self.assertTrue(summary.endswith("."))


class ToolTierTests(unittest.TestCase):
    def test_checking_a_gate_is_a_read(self) -> None:
        """`gate_check` computes requirements from current state and writes
        nothing. Marked as a mutation it cost a person an approval prompt for
        asking a question."""
        gate = next(tool for tool in TOOLS if tool.name == "loopforge_gate")
        self.assertEqual(gate.tier, TIER_READ)
        self.assertFalse(gate.mutates)

    def test_producing_evidence_is_not_making_a_claim(self) -> None:
        """The distinction `allow-edit` turns on. A build result is work; a
        stage transition is an assertion that cites it."""
        by_name = {tool.name: tool for tool in TOOLS}
        self.assertEqual(by_name["loopforge_run"].tier, TIER_EVIDENCE)
        self.assertEqual(by_name["loopforge_capture"].tier, TIER_EVIDENCE)
        self.assertEqual(by_name["loopforge_advance"].tier, TIER_CLAIM)

    def test_a_tool_cannot_be_given_a_tier_that_does_not_exist(self) -> None:
        """A typo in a tier would otherwise publish the tool as unplaceable and
        ask about it forever, which reads as a broken tool rather than a
        misspelling."""
        from loopforge.mcp import NO_ARGUMENTS, Tool

        with self.assertRaises(ValueError):
            Tool("x", "d", NO_ARGUMENTS, lambda p, a: None, tier="mutating")
