"""User-level storage.

This is where credentials live, so the tests care as much about what the store
refuses and what it protects as about what it records.
"""

from __future__ import annotations

import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path

from loopforge.userstore import SCHEMA_VERSION, UserStore, UserStoreError, user_home


class UserHomeTests(unittest.TestCase):
    def test_the_home_is_overridable_so_tests_never_touch_a_real_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            os.environ["LOOPFORGE_HOME"] = directory
            try:
                self.assertEqual(user_home(), Path(directory))
            finally:
                del os.environ["LOOPFORGE_HOME"]

    def test_it_defaults_under_the_user_home(self) -> None:
        os.environ.pop("LOOPFORGE_HOME", None)
        self.assertEqual(user_home(), Path.home() / ".loopforge")


class StoreFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name) / "home"
        self.store = UserStore(self.home)

    def tearDown(self) -> None:
        self.temporary.cleanup()


class ProtectionTests(StoreFixture):
    def test_the_database_is_created_owner_only(self) -> None:
        """It holds API keys. A permissive umask must not decide this."""
        previous = os.umask(0o022)
        try:
            self.store.save_provider("openai_compatible", "https://x.test/v1", "sk-1", "m")
        finally:
            os.umask(previous)

        mode = stat.S_IMODE(self.store.path.stat().st_mode)
        self.assertEqual(mode, 0o600, oct(mode))

    def test_the_directory_is_created_owner_only(self) -> None:
        previous = os.umask(0o022)
        try:
            self.store.save_operator("op_1", "Ada")
        finally:
            os.umask(previous)

        mode = stat.S_IMODE(self.home.stat().st_mode)
        self.assertEqual(mode, 0o700, oct(mode))

    def test_a_missing_home_is_created(self) -> None:
        self.assertFalse(self.home.exists())
        self.store.preferences()
        self.assertTrue(self.home.is_dir())


class MigrationTests(StoreFixture):
    def test_a_fresh_database_lands_on_the_current_schema(self) -> None:
        self.store.preferences()
        with sqlite3.connect(self.store.path) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, SCHEMA_VERSION)

    def test_opening_twice_does_not_rerun_migrations(self) -> None:
        self.store.save_operator("op_1", "Ada")
        self.store.save_operator("op_1", "Ada L")
        self.assertEqual(self.store.operator()["name"], "Ada L")

    def test_a_newer_schema_is_refused_rather_than_migrated_backwards(self) -> None:
        """Silently operating on a database this build does not understand
        would be how records get truncated or lost."""
        self.store.preferences()
        with sqlite3.connect(self.store.path) as connection:
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

        with self.assertRaises(UserStoreError) as caught:
            self.store.preferences()
        self.assertEqual(caught.exception.code, "USER_STORE_TOO_NEW")


class TimestampFormatTests(StoreFixture):
    """The format is a contract between two writers.

    The desktop shell writes this column too, in Rust, and both order it as
    text. If the two formats disagree by a field width, sorting silently
    breaks and the recent-project list comes back in the wrong order. The
    matching assertion lives in `src-tauri/src/userstore.rs`.
    """

    def test_the_timestamp_is_fixed_width_utc_microseconds(self) -> None:
        import re

        self.store.remember_project("/a")
        stamp = self.store.recent_projects()[0]["last_opened_at"]

        self.assertRegex(stamp, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
        # Fixed width is the property that makes text ordering correct.
        self.assertEqual(len(stamp), 27)


class ProviderTests(StoreFixture):
    def test_a_provider_round_trips(self) -> None:
        saved = self.store.save_provider(
            "openai_compatible", "https://api.example.test/v1", "sk-secret", "some-model"
        )
        self.assertEqual(saved["base_url"], "https://api.example.test/v1")
        self.assertEqual(saved["model"], "some-model")
        self.assertEqual(self.store.provider("openai_compatible")["api_key"], "sk-secret")

    def test_an_empty_key_keeps_the_stored_one(self) -> None:
        """So a surface can change a base URL without ever reading the
        credential back out, and a user need not retype it."""
        self.store.save_provider("openai_compatible", "https://a.test/v1", "sk-secret", "m1")

        self.store.save_provider("openai_compatible", "https://b.test/v1", "", "m2")

        stored = self.store.provider("openai_compatible")
        self.assertEqual(stored["api_key"], "sk-secret")
        self.assertEqual(stored["base_url"], "https://b.test/v1")
        self.assertEqual(stored["model"], "m2")

    def test_an_unknown_provider_is_absent_rather_than_empty(self) -> None:
        self.assertIsNone(self.store.provider("nothing"))

    def test_a_blank_provider_id_is_refused(self) -> None:
        for value in ("", "   "):
            with self.subTest(value=value), self.assertRaises(UserStoreError) as caught:
                self.store.save_provider(value, "https://x.test", "k", "m")
            self.assertEqual(caught.exception.code, "PROVIDER_ID_INVALID")

    def test_a_provider_carries_its_name_and_protocol(self) -> None:
        """Added in schema 2. A source picked from a list needs a name to be
        recognised by later, and the protocol says how it is spoken to."""
        saved = self.store.save_provider(
            "openai_compatible",
            "https://api.deepseek.com/v1",
            "sk-1",
            "deepseek-chat",
            display_name="DeepSeek",
            protocol="openai_compatible",
        )
        self.assertEqual(saved["display_name"], "DeepSeek")
        self.assertEqual(saved["protocol"], "openai_compatible")

    def test_a_provider_saved_without_them_still_has_a_protocol(self) -> None:
        """The column defaults rather than being nullable: every endpoint is
        spoken to somehow, and a blank protocol would have no meaning."""
        saved = self.store.save_provider("openai_compatible", "https://x.test/v1", "k", "m")
        self.assertEqual(saved["protocol"], "openai_compatible")
        self.assertEqual(saved["display_name"], "")

    def test_an_existing_store_gains_the_new_columns(self) -> None:
        """The migration path, not just the fresh-database one: a store
        created before schema 2 must come forward without losing its rows."""
        import sqlite3

        # A schema-1 store with a provider already in it.
        self.store.home.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.store.path) as connection:
            connection.executescript(
                """
                CREATE TABLE providers (
                    provider_id TEXT PRIMARY KEY,
                    base_url    TEXT NOT NULL DEFAULT '',
                    api_key     TEXT NOT NULL DEFAULT '',
                    model       TEXT NOT NULL DEFAULT '',
                    updated_at  TEXT NOT NULL
                );
                CREATE TABLE operator (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    id TEXT NOT NULL, name TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE projects (
                    path TEXT PRIMARY KEY, last_opened_at TEXT NOT NULL,
                    last_mode TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO providers VALUES ('openai_compatible', 'https://old.test/v1',
                    'sk-old', 'old-model', '2026-01-01T00:00:00.000000Z');
                PRAGMA user_version = 1;
                """
            )

        migrated = self.store.provider("openai_compatible")

        self.assertEqual(migrated["api_key"], "sk-old", "the credential survived")
        self.assertEqual(migrated["base_url"], "https://old.test/v1")
        self.assertEqual(migrated["protocol"], "openai_compatible")
        self.assertEqual(migrated["display_name"], "")

    def test_forgetting_a_provider_reports_whether_it_existed(self) -> None:
        self.store.save_provider("openai_compatible", "https://x.test/v1", "k", "m")
        self.assertTrue(self.store.forget_provider("openai_compatible"))
        self.assertFalse(self.store.forget_provider("openai_compatible"))
        self.assertIsNone(self.store.provider("openai_compatible"))


class OperatorTests(StoreFixture):
    def test_there_is_at_most_one_operator(self) -> None:
        """A machine has one person at it, and an approval names them. Two rows
        would mean two answers to "who approved this"."""
        self.store.save_operator("op_1", "Ada")
        self.store.save_operator("op_2", "Grace")

        with sqlite3.connect(self.store.path) as connection:
            count = connection.execute("SELECT count(*) FROM operator").fetchone()[0]
        self.assertEqual(count, 1)
        self.assertEqual(self.store.operator(), {"id": "op_2", "name": "Grace"})

    def test_absence_is_reported_rather_than_invented(self) -> None:
        self.assertIsNone(self.store.operator())

    def test_a_blank_id_is_refused(self) -> None:
        with self.assertRaises(UserStoreError) as caught:
            self.store.save_operator("  ", "Ada")
        self.assertEqual(caught.exception.code, "OPERATOR_ID_INVALID")


class ProjectTests(StoreFixture):
    def test_projects_come_back_most_recent_first(self) -> None:
        """Ordering is by timestamp, so the timestamp has to be finer than the
        interval between two calls -- at second resolution these two sorted
        arbitrarily."""
        self.store.remember_project("/a", "chat")
        self.store.remember_project("/b", "flow")

        paths = [item["path"] for item in self.store.recent_projects()]
        self.assertEqual(paths[0], "/b")
        self.assertIn("/a", paths)

    def test_reopening_updates_rather_than_duplicates(self) -> None:
        self.store.remember_project("/a", "chat")
        self.store.remember_project("/a", "tasks")

        recorded = self.store.recent_projects()
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]["last_mode"], "tasks")

    def test_the_listing_is_bounded(self) -> None:
        for index in range(5):
            self.store.remember_project(f"/p{index}")
        self.assertEqual(len(self.store.recent_projects(limit=2)), 2)

    def test_forgetting_a_project_reports_whether_it_existed(self) -> None:
        self.store.remember_project("/a")
        self.assertTrue(self.store.forget_project("/a"))
        self.assertFalse(self.store.forget_project("/a"))


class PreferenceTests(StoreFixture):
    def test_preferences_round_trip_and_merge(self) -> None:
        self.store.save_preferences({"theme": "dark", "locale": "zh-Hans"})
        self.store.save_preferences({"theme": "light"})

        self.assertEqual(
            self.store.preferences(), {"theme": "light", "locale": "zh-Hans"}
        )

    def test_an_empty_store_has_no_preferences(self) -> None:
        self.assertEqual(self.store.preferences(), {})


if __name__ == "__main__":
    unittest.main()
