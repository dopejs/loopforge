"""The hypothesis projection: structured fields in, core records out."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from loopforge.project import HYPOTHESIS_FIELDS, LoopforgeProject, parse_hypothesis
from loopforge_agent.application import LoopforgeAgent, LoopforgeAgentError


def complete_fields() -> dict[str, str]:
    return {key: f"value for {key}" for key in HYPOTHESIS_FIELDS}


class HypothesisRenderingTests(unittest.TestCase):
    def test_rendered_markdown_parses_back_to_the_same_fields(self) -> None:
        """The heading contract, pinned.

        Headings are derived from field names and matched by the core after
        normalisation. If that correspondence broke, the core would parse an
        empty value rather than fail, and the hypothesis would be recorded with
        silently missing content.
        """
        fields = complete_fields()
        parsed = parse_hypothesis(LoopforgeAgent._hypothesis_markdown(fields), ".md")
        self.assertEqual(parsed, fields)

    def test_every_declared_field_gets_a_heading(self) -> None:
        markdown = LoopforgeAgent._hypothesis_markdown(complete_fields())
        for key in HYPOTHESIS_FIELDS:
            self.assertIn(f"## {key.replace('_', ' ').title()}", markdown)


class DraftParsingTests(unittest.TestCase):
    """The lenient parser used for drafts, which the strict one cannot serve."""

    def test_a_partial_draft_keeps_what_the_model_answered(self) -> None:
        """The core's parser raises on an incomplete document. A draft has to
        survive that: nine good sections are nine fewer for the user to write.
        """
        markdown = "## Platform\nWeb\n\n## Core Verb\nCharge\n"
        parsed = LoopforgeAgent._parse_draft(markdown)
        self.assertEqual(parsed["platform"], "Web")
        self.assertEqual(parsed["core_verb"], "Charge")

    def test_headings_the_model_invents_are_ignored(self) -> None:
        """Guessing at an unrecognised heading would put text in a field the
        model never meant to answer."""
        parsed = LoopforgeAgent._parse_draft(
            "## Platform\nWeb\n\n## Monetisation\nNone\n"
        )
        self.assertEqual(set(parsed), {"platform"})

    def test_the_short_heading_aliases_are_honoured(self) -> None:
        """The core accepts `## Loop` for moment_to_moment_loop; a draft parsed
        by a stricter rule would silently drop it."""
        parsed = LoopforgeAgent._parse_draft("## Loop\nDodge then charge\n")
        self.assertEqual(parsed["moment_to_moment_loop"], "Dodge then charge")

    def test_prose_before_the_first_heading_is_discarded(self) -> None:
        parsed = LoopforgeAgent._parse_draft("Sure! Here you go.\n\n## Platform\nWeb\n")
        self.assertEqual(parsed, {"platform": "Web"})


class HypothesisAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.agent = object.__new__(LoopforgeAgent)
        self.agent.project = LoopforgeProject(self.root)
        self.agent.project.init()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_absence_is_a_state_with_every_field_listed_as_missing(self) -> None:
        result = self.agent.hypothesis()
        self.assertEqual(result["schema_version"], "loopforge-hypothesis-v1")
        self.assertFalse(result["present"])
        # The surface needs the full field list to render a draft form before
        # anything exists.
        self.assertEqual(result["missing"], list(HYPOTHESIS_FIELDS))
        self.assertEqual(set(result["fields"]), set(HYPOTHESIS_FIELDS))

    def test_a_complete_hypothesis_is_recorded_and_read_back(self) -> None:
        fields = complete_fields()
        created = self.agent.create_hypothesis(fields)

        self.assertTrue(created["present"])
        self.assertEqual(created["missing"], [])
        self.assertEqual(created["revision"], 1)
        self.assertEqual(created["fields"], fields)

        # A fresh projection reads the same record from the event log.
        self.assertEqual(self.agent.hypothesis()["fields"], fields)

    def test_a_revision_increments_rather_than_replacing(self) -> None:
        self.agent.create_hypothesis(complete_fields())
        revised = dict(complete_fields(), hypothesis="a sharper claim")

        result = self.agent.create_hypothesis(revised)

        self.assertEqual(result["revision"], 2)
        self.assertEqual(result["fields"]["hypothesis"], "a sharper claim")

    def test_incomplete_fields_are_refused_and_named(self) -> None:
        """The gate would refuse this later with less context, so the caller is
        told which fields are empty at submission time."""
        fields = dict(complete_fields(), keep_signals="", kill_signals="   ")

        with self.assertRaises(LoopforgeAgentError) as caught:
            self.agent.create_hypothesis(fields)

        self.assertEqual(caught.exception.code, "HYPOTHESIS_INCOMPLETE")
        self.assertIn("keep_signals", str(caught.exception))
        self.assertIn("kill_signals", str(caught.exception))
        self.assertFalse(self.agent.hypothesis()["present"], "nothing was recorded")

    def test_unknown_fields_are_refused(self) -> None:
        """Silently dropping an unknown key would let a caller believe it had
        recorded something the core never stored."""
        with self.assertRaises(LoopforgeAgentError) as caught:
            self.agent.create_hypothesis(dict(complete_fields(), smell="pine"))
        self.assertEqual(caught.exception.code, "HYPOTHESIS_FIELDS_INVALID")
        self.assertIn("smell", str(caught.exception))

    def test_a_non_object_payload_is_refused(self) -> None:
        for value in ("text", ["a"], None, 7):
            with self.subTest(value=value), self.assertRaises(LoopforgeAgentError):
                self.agent.create_hypothesis(value)

    def test_an_oversized_field_is_refused(self) -> None:
        fields = dict(complete_fields(), constraints="x" * 4_001)
        with self.assertRaises(LoopforgeAgentError) as caught:
            self.agent.create_hypothesis(fields)
        self.assertEqual(caught.exception.code, "HYPOTHESIS_FIELDS_INVALID")

    def test_a_partial_approval_is_refused_by_the_core(self) -> None:
        """Approver id, name and rationale are recorded together or not at
        all; half an approval would attribute a decision to nobody."""
        with self.assertRaises(Exception) as caught:
            self.agent.create_hypothesis(complete_fields(), approver_id="op_1")
        self.assertIn("APPROVAL_INCOMPLETE", str(getattr(caught.exception, "diagnostic_code", "")))

    def test_a_complete_approval_is_recorded(self) -> None:
        result = self.agent.create_hypothesis(
            complete_fields(),
            approver_id="op_1",
            approver_name="Local Operator",
            rationale="Reviewed the draft and agreed with the claim.",
        )
        self.assertTrue(result["present"])


class HypothesisContractTests(unittest.TestCase):
    """The contract is the shared definition; drift here is silent elsewhere."""

    def _schema(self) -> dict:
        import json

        root = Path(__file__).resolve().parents[2]
        return json.loads(
            (root / "contracts" / "loopforge-hypothesis-v1.schema.json").read_text()
        )

    def test_the_schema_lists_exactly_the_core_fields(self) -> None:
        """A field added to the core but not the contract would be dropped by
        the Workbench without any layer reporting a problem."""
        properties = self._schema()["properties"]["fields"]["properties"]
        self.assertEqual(list(properties), list(HYPOTHESIS_FIELDS))

    def test_the_projection_stays_within_the_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            agent = object.__new__(LoopforgeAgent)
            agent.project = LoopforgeProject(Path(directory))
            agent.project.init()
            agent.create_hypothesis(complete_fields())
            result = agent.hypothesis()

        schema = self._schema()
        self.assertLessEqual(set(result), set(schema["properties"]))
        self.assertEqual(set(result["fields"]), set(HYPOTHESIS_FIELDS))


if __name__ == "__main__":
    unittest.main()
