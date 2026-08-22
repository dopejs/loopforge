"""Capture registration and the evidence listing a decision cites."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from loopforge.project import LoopforgeProject
from loopforge_agent.application import LoopforgeAgent, LoopforgeAgentError

# A one-pixel PNG. Real bytes rather than a stub, because the core checksums
# the file it is given.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


class CaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.agent = object.__new__(LoopforgeAgent)
        self.agent.project = LoopforgeProject(self.root)
        self.agent.project.init()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _screenshot(self, name: str = "shot.png", inside: bool = True) -> Path:
        directory = self.root if inside else Path(tempfile.mkdtemp())
        path = directory / name
        path.write_bytes(PNG)
        return path

    def test_a_capture_is_registered_as_a_manual_observation(self) -> None:
        """Trust level and result are the point. Engine runs produce
        tool_generated evidence; a screenshot a person chose is weaker, and a
        later reader has to be able to tell them apart."""
        result = self.agent.register_capture(str(self._screenshot()))

        evidence = result["evidence"]
        self.assertEqual(result["schema_version"], "loopforge-evidence-v1")
        self.assertEqual(evidence["type"], "capture")
        self.assertEqual(evidence["trust_level"], "manually_imported")
        self.assertEqual(evidence["result"], "observation")
        self.assertEqual(evidence["path_kind"], "project-relative")

    def test_a_capture_satisfies_the_visual_claim(self) -> None:
        self.assertEqual(
            self.agent.project_status()["claims"][1]["status"], "unknown"
        )
        self.agent.register_capture(str(self._screenshot()))
        claims = {c["claim"]: c["status"] for c in self.agent.project_status()["claims"]}
        self.assertEqual(claims["VISUALLY_REVIEWED"], "satisfied")
        # Orthogonal claims stay orthogonal: a screenshot proves nothing about
        # whether the project builds (ADR 0002).
        self.assertEqual(claims["TECHNICALLY_VALIDATED"], "unknown")

    def test_a_file_outside_the_project_is_recorded_as_a_reference(self) -> None:
        """The core does not copy the file. An outside path is only referenced,
        so moving it later breaks the link -- the surface warns about this and
        it must stay observable here."""
        result = self.agent.register_capture(str(self._screenshot(inside=False)))
        self.assertEqual(result["evidence"]["path_kind"], "absolute")

    def test_a_missing_file_is_refused(self) -> None:
        with self.assertRaises(Exception) as caught:
            self.agent.register_capture(str(self.root / "absent.png"))
        self.assertEqual(
            getattr(caught.exception, "diagnostic_code", ""), "EVIDENCE_FILE_MISSING"
        )

    def test_an_empty_path_is_refused_before_the_core(self) -> None:
        for value in ("", "   "):
            with self.subTest(value=value), self.assertRaises(LoopforgeAgentError) as caught:
                self.agent.register_capture(value)
            self.assertEqual(caught.exception.code, "CAPTURE_PATH_INVALID")


class EvidenceListingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.agent = object.__new__(LoopforgeAgent)
        self.agent.project = LoopforgeProject(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_an_uninitialized_project_lists_nothing_rather_than_failing(self) -> None:
        """A decision surface asking for evidence before init is a normal
        ordering, not an error."""
        self.assertEqual(self.agent.evidence()["evidence"], [])

    def test_evidence_is_listed_newest_first_with_its_trust_level(self) -> None:
        self.agent.project.init()
        for name in ("first.png", "second.png"):
            path = self.root / name
            path.write_bytes(PNG)
            self.agent.register_capture(str(path))

        listed = self.agent.evidence()["evidence"]

        self.assertEqual(len(listed), 2)
        self.assertEqual(listed[0]["path"], "second.png")
        self.assertTrue(all(item["trust_level"] == "manually_imported" for item in listed))
        self.assertTrue(all(item["id"] for item in listed))


if __name__ == "__main__":
    unittest.main()
