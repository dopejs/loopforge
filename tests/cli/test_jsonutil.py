"""Atomic JSON writing, including permissions for credential files."""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from loopforge.jsonutil import atomic_write_json, atomic_write_text


class AtomicWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="loopforge-jsonutil-"))
        # A permissive umask, so the test proves `mode` does the work rather
        # than inheriting a strict developer default.
        self.previous_umask = os.umask(0o022)
        self.addCleanup(os.umask, self.previous_umask)

    def test_writes_are_owner_only_even_under_a_permissive_umask(self) -> None:
        """Not the umask's doing: the temporary file is created via mkstemp
        semantics at 0600 and `os.replace` preserves that. Asserted because it
        is what protects the daemon token, and a future change to how the
        temporary file is created could silently widen it."""
        path = self.root / "plain.json"
        atomic_write_json(path, {"a": 1})
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_an_explicit_mode_is_applied(self) -> None:
        """Callers holding a credential state the intent rather than relying on
        the implicit default above."""
        path = self.root / "secret.json"
        atomic_write_json(path, {"token": "kura_secret"}, mode=0o600)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_an_explicit_mode_can_widen_a_non_secret_file(self) -> None:
        path = self.root / "shared.json"
        atomic_write_json(path, {"a": 1}, mode=0o644)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)

    def test_rewriting_keeps_the_restricted_mode(self) -> None:
        path = self.root / "secret.json"
        atomic_write_json(path, {"token": "one"}, mode=0o600)
        atomic_write_json(path, {"token": "two"}, mode=0o600)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_text_writes_share_the_same_guarantees(self) -> None:
        """Both writers are used for project state; a difference between them
        would be a trap rather than a design."""
        path = self.root / "note.md"
        atomic_write_text(path, "hello")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(path.read_text(encoding="utf-8"), "hello")

        widened = self.root / "shared.md"
        atomic_write_text(widened, "hello", file_mode=0o644)
        self.assertEqual(stat.S_IMODE(widened.stat().st_mode), 0o644)

    def test_no_temporary_file_survives(self) -> None:
        path = self.root / "value.json"
        atomic_write_json(path, {"a": 1}, mode=0o600)
        leftovers = [p.name for p in self.root.iterdir() if p.name != "value.json"]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
