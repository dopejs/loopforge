"""Engine run projection: the data behind the Terminal and Test workspaces."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from loopforge_agent.runs import MAX_OUTPUT_CHARS, MAX_RUNS, RunStore


def write_run(directory: Path, run_id: str, **overrides: object) -> None:
    record = {
        "schema_version": 1,
        "run_id": run_id,
        "operation": "test",
        "adapter": "godot",
        "adapter_version": "4.2",
        "command": ["godot4", "--headless"],
        "cwd": "/tmp/game",
        "started_at": "2026-08-22T00:00:00Z",
        "finished_at": "2026-08-22T00:00:05Z",
        "status": "completed",
        "exit_code": 0,
        "timed_out": False,
        "stdout": "ok",
        "stderr": "",
    }
    record.update(overrides)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{run_id}.json").write_text(json.dumps(record), encoding="utf-8")


class RunStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="loopforge-runs-"))
        self.store = RunStore(self.root)
        self.directory = self.root / ".loopforge" / "runs"

    def test_a_project_with_no_runs_lists_empty(self) -> None:
        self.assertEqual(self.store.list(), [])

    def test_listing_is_newest_first_and_omits_output(self) -> None:
        write_run(self.directory, "run_a", started_at="2026-08-22T00:00:00Z")
        write_run(self.directory, "run_b", started_at="2026-08-22T01:00:00Z")

        listed = self.store.list()
        self.assertEqual([r["id"] for r in listed], ["run_b", "run_a"])
        # The list view never needs process output, which can be megabytes.
        self.assertNotIn("stdout", listed[0])

    def test_listing_can_be_narrowed_to_one_operation(self) -> None:
        write_run(self.directory, "run_build", operation="build")
        write_run(self.directory, "run_test", operation="test")
        self.assertEqual([r["id"] for r in self.store.list("test")], ["run_test"])
        self.assertEqual([r["id"] for r in self.store.list("build")], ["run_build"])

    def test_detail_includes_bounded_output(self) -> None:
        write_run(self.directory, "run_x", stdout="hello", stderr="warn")
        detail = self.store.read("run_x")
        assert detail is not None
        self.assertEqual(detail["stdout"], "hello")
        self.assertEqual(detail["stderr"], "warn")
        self.assertEqual(detail["command"], ["godot4", "--headless"])

    def test_huge_output_is_truncated_keeping_the_end(self) -> None:
        """The tail carries the failure; the head is usually boilerplate."""
        write_run(self.directory, "run_big", stdout="A" * 10 + "B" * (MAX_OUTPUT_CHARS + 50))
        detail = self.store.read("run_big")
        assert detail is not None
        self.assertLess(len(detail["stdout"]), MAX_OUTPUT_CHARS + 200)
        self.assertTrue(detail["stdout"].rstrip().endswith("B"))
        self.assertIn("truncated", detail["stdout"])

    def test_an_unreadable_record_is_skipped_not_fatal(self) -> None:
        write_run(self.directory, "run_ok")
        (self.directory / "broken.json").write_text("{not json", encoding="utf-8")
        self.assertEqual([r["id"] for r in self.store.list()], ["run_ok"])

    def test_an_unknown_status_is_not_coerced_into_failure(self) -> None:
        """A newer core may add statuses; reporting them as failed would lie."""
        write_run(self.directory, "run_new", status="queued")
        (summary,) = self.store.list()
        self.assertEqual(summary["status"], "unknown")

    def test_a_missing_exit_code_stays_absent(self) -> None:
        write_run(self.directory, "run_t", exit_code=None, status="interrupted", timed_out=True)
        (summary,) = self.store.list()
        self.assertIsNone(summary["exit_code"])
        self.assertTrue(summary["timed_out"])

    def test_ids_that_could_escape_the_directory_are_refused(self) -> None:
        write_run(self.directory, "run_ok")
        for hostile in ["../run_ok", "a/b", "", "x" * 65]:
            self.assertIsNone(self.store.read(hostile))

    def test_listing_is_bounded(self) -> None:
        for index in range(MAX_RUNS + 10):
            write_run(self.directory, f"run_{index:04d}", started_at=f"2026-08-22T00:{index % 60:02d}:00Z")
        self.assertEqual(len(self.store.list()), MAX_RUNS)


if __name__ == "__main__":
    unittest.main()
