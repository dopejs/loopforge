"""Reading and writing the project's own files.

Loopforge published ten tools and every one of them was bookkeeping: stage,
revision, evidence, approval. None of them touched a file. So an agent asked to
build a Sudoku game did the only thing it could -- it wrote the C# into its
reply and told the person to paste it -- and that read as laziness when it was
a missing capability.

The refusals here are the interesting part. A tool that can write anywhere is a
tool that can rewrite the event log, follow a symlink out of the project, or
replace a file nobody looked at.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from loopforge.mcp import TOOLS, _SEEN
from loopforge.project import LoopforgeProject


def tool(name: str):
    found = next((t for t in TOOLS if t.name == name), None)
    assert found is not None, name
    return found


class FileTools(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.project = LoopforgeProject(self.root)
        _SEEN.clear()

    def tearDown(self) -> None:
        _SEEN.clear()
        self.temporary.cleanup()

    def _run(self, name: str, **arguments):
        return tool(name).run(self.project, arguments)

    # -- the ordinary case --------------------------------------------------

    def test_writes_a_file_the_project_did_not_have(self) -> None:
        answer = self._run(
            "loopforge_write", path="Assets/SudokuGrid.cs", content="public class SudokuGrid {}"
        )

        self.assertTrue(answer["created"])
        self.assertEqual(
            (self.root / "Assets" / "SudokuGrid.cs").read_text(encoding="utf-8"),
            "public class SudokuGrid {}",
        )

    def test_reads_one_back(self) -> None:
        (self.root / "a.cs").write_text("hello", encoding="utf-8")

        self.assertEqual(self._run("loopforge_read", path="a.cs")["content"], "hello")

    def test_lists_what_is_there(self) -> None:
        (self.root / "Assets").mkdir()
        (self.root / "a.cs").write_text("x", encoding="utf-8")

        entries = self._run("loopforge_list")["entries"]

        self.assertEqual([e["path"] for e in entries], ["Assets", "a.cs"])
        self.assertEqual([e["kind"] for e in entries], ["directory", "file"])

    def test_edits_part_of_a_file(self) -> None:
        (self.root / "a.cs").write_text("int size = 9;\nint blocks = 3;\n", encoding="utf-8")

        self._run("loopforge_edit", path="a.cs", old_string="size = 9", new_string="size = 16")

        self.assertIn("size = 16", (self.root / "a.cs").read_text(encoding="utf-8"))

    # -- the refusals -------------------------------------------------------

    def test_will_not_write_outside_the_project(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self._run("loopforge_write", path="../escaped.cs", content="x")
        self.assertIn("outside the project", str(caught.exception))
        self.assertFalse((self.root.parent / "escaped.cs").exists())

    def test_will_not_follow_a_symlink_out_of_the_project(self) -> None:
        # Resolved before it is checked. A link is the way a path inside the
        # project names a file that is not.
        outside = Path(tempfile.mkdtemp()) / "secret.txt"
        outside.write_text("private", encoding="utf-8")
        os.symlink(outside, self.root / "link.txt")

        # On the message, not merely on the type. A first version of this
        # asserted `ValueError` and passed with the confinement check removed:
        # the read failed anyway, deeper in, when `relative_to` could not place
        # the resolved path. Same exception, different reason, and the test
        # would not have noticed the guard going away.
        for call in (
            lambda: self._run("loopforge_read", path="link.txt"),
            lambda: self._run("loopforge_write", path="link.txt", content="x"),
        ):
            with self.assertRaises(ValueError) as caught:
                call()
            self.assertIn("outside the project", str(caught.exception))
        self.assertEqual(outside.read_text(encoding="utf-8"), "private")

    def test_will_not_write_loopforge_s_own_records(self) -> None:
        # The event log is a hash chain and the state is derived from it. An
        # edit here is not a change to the project, it is a forged history --
        # and `loopforge_validate` exists to catch exactly that.
        records = self.root / ".loopforge"
        records.mkdir()
        (records / "events.jsonl").write_text("{}\n", encoding="utf-8")

        with self.assertRaises(ValueError) as caught:
            self._run("loopforge_write", path=".loopforge/events.jsonl", content="forged")

        self.assertIn("Loopforge's own record", str(caught.exception))
        self.assertEqual((records / "events.jsonl").read_text(encoding="utf-8"), "{}\n")

    def test_will_not_edit_loopforge_s_own_records_either(self) -> None:
        records = self.root / ".loopforge"
        records.mkdir()
        (records / "state.json").write_text('{"stage": "DISCOVERY"}', encoding="utf-8")

        with self.assertRaises(ValueError):
            self._run(
                "loopforge_edit",
                path=".loopforge/state.json",
                old_string="DISCOVERY",
                new_string="PROTOTYPING",
            )

    def test_will_not_overwrite_a_file_nobody_looked_at(self) -> None:
        # The refusal that is about the person rather than the model. Writing
        # over a file it has not read replaces whatever was there with what the
        # model believes should be there, and the difference is work that is
        # simply gone.
        (self.root / "a.cs").write_text("someone's work", encoding="utf-8")

        with self.assertRaises(ValueError) as caught:
            self._run("loopforge_write", path="a.cs", content="replaced")

        self.assertIn("has not been read", str(caught.exception))
        self.assertEqual((self.root / "a.cs").read_text(encoding="utf-8"), "someone's work")

    def test_overwrites_once_it_has_been_read(self) -> None:
        (self.root / "a.cs").write_text("old", encoding="utf-8")
        self._run("loopforge_read", path="a.cs")

        self._run("loopforge_write", path="a.cs", content="new")

        self.assertEqual((self.root / "a.cs").read_text(encoding="utf-8"), "new")

    def test_refuses_an_edit_that_could_land_in_two_places(self) -> None:
        # Replacing the first of several is how an edit lands somewhere nobody
        # meant, and it is invisible afterwards: the file still compiles and
        # says something else.
        (self.root / "a.cs").write_text("x = 1;\nx = 1;\n", encoding="utf-8")

        with self.assertRaises(ValueError) as caught:
            self._run("loopforge_edit", path="a.cs", old_string="x = 1;", new_string="x = 2;")

        self.assertIn("appears 2 times", str(caught.exception))
        self.assertEqual((self.root / "a.cs").read_text(encoding="utf-8"), "x = 1;\nx = 1;\n")

    def test_refuses_an_edit_whose_target_is_not_there(self) -> None:
        (self.root / "a.cs").write_text("y = 1;", encoding="utf-8")

        with self.assertRaises(ValueError) as caught:
            self._run("loopforge_edit", path="a.cs", old_string="x = 1;", new_string="x = 2;")

        self.assertIn("does not appear", str(caught.exception))

    def test_says_a_binary_file_is_not_text_rather_than_mangling_it(self) -> None:
        # A model handed replacement characters would try to edit them back.
        (self.root / "sprite.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")

        with self.assertRaises(ValueError) as caught:
            self._run("loopforge_read", path="sprite.png")

        self.assertIn("not text", str(caught.exception))

    def test_truncates_a_file_too_large_to_hand_over_and_says_so(self) -> None:
        # A silently shortened file is one a model reasons about as though it
        # had seen the whole.
        from loopforge.mcp import MAX_FILE_CHARS

        (self.root / "big.txt").write_text("x" * (MAX_FILE_CHARS + 500), encoding="utf-8")

        answer = self._run("loopforge_read", path="big.txt")

        self.assertTrue(answer["truncated"])
        self.assertEqual(len(answer["content"]), MAX_FILE_CHARS)
        self.assertEqual(answer["total_characters"], MAX_FILE_CHARS + 500)


class WhatTheModesAllow(unittest.TestCase):
    """`allow-edit` had nothing to allow until there were files to edit."""

    def test_edits_are_asked_about_under_ask(self) -> None:
        from loopforge.permissions import MODE_ASK, exposure_for
        from loopforge.mcp import TIER_EDIT

        self.assertEqual(exposure_for(TIER_EDIT, MODE_ASK), "approval_required")

    def test_allow_edit_finally_allows_an_edit(self) -> None:
        from loopforge.permissions import MODE_ALLOW_EDIT, exposure_for
        from loopforge.mcp import TIER_EDIT

        self.assertEqual(exposure_for(TIER_EDIT, MODE_ALLOW_EDIT), "allow")

    def test_but_still_asks_before_a_claim(self) -> None:
        # The distinction the name rests on: writing a script changes the game,
        # advancing a stage changes Loopforge's record of it. Someone who said
        # "allow edits" did not say the agent may decide their prototype
        # passed.
        from loopforge.permissions import MODE_ALLOW_EDIT, exposure_for
        from loopforge.mcp import TIER_CLAIM

        self.assertEqual(exposure_for(TIER_CLAIM, MODE_ALLOW_EDIT), "approval_required")

    def test_every_published_tool_has_a_tier_every_mode_can_place(self) -> None:
        # A tool whose kind cannot be placed is one nobody has decided about,
        # and a new tool must not arrive silently allowed.
        from loopforge.permissions import MODES, exposure_for
        from loopforge.mcp import TIERS

        for published in TOOLS:
            self.assertIn(published.tier, TIERS, published.name)
            for mode in MODES:
                self.assertIn(
                    exposure_for(published.tier, mode),
                    {"allow", "approval_required"},
                    f"{published.name} under {mode}",
                )


if __name__ == "__main__":
    unittest.main()
