"""User-level storage: what belongs to the person, not to a project.

`.loopforge/` inside a repository is project state -- the event log, evidence
and derived snapshot that travel with the project and are meant to be read,
copied and committed alongside it. This is the other half: provider
credentials, the operator's identity, which projects they have opened, their
interface preferences. None of that belongs to any one game, and
`docs/cli.md` already says secrets must not live in project files.

SQLite rather than a spread of JSON files because these records are related,
several are lists that grow, and migrations need to be explicit rather than
"whatever shape the file happened to have". It is not an encryption boundary:
a key stored here is plaintext protected by file permissions, exactly as it
would be in JSON. The database is created 0600 and the directory 0700, and
nothing more is claimed than that.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 4

#: Overridable so tests never touch a developer's real store.
HOME_VARIABLE = "LOOPFORGE_HOME"


def user_home() -> Path:
    """The directory holding user-level Loopforge state."""
    override = os.environ.get(HOME_VARIABLE, "").strip()
    return Path(override).expanduser() if override else Path.home() / ".loopforge"


def _utc_now() -> str:
    """A sortable UTC timestamp.

    Microseconds, not seconds: these strings order the recent-project list, and
    at second resolution two projects opened in the same second sort
    arbitrarily. A test caught exactly that.
    """
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


#: Applied in order; each is a complete statement list for one version step.
#: Never edited once shipped -- a new version is a new entry, so an existing
#: database upgrades by the same path every time.
MIGRATIONS: tuple[tuple[str, ...], ...] = (
    (
        """
        CREATE TABLE providers (
            provider_id TEXT PRIMARY KEY,
            base_url    TEXT NOT NULL DEFAULT '',
            api_key     TEXT NOT NULL DEFAULT '',
            model       TEXT NOT NULL DEFAULT '',
            updated_at  TEXT NOT NULL
        )
        """,
        # One row, enforced by the constant primary key: there is one person
        # using this machine, and an approval names them.
        """
        CREATE TABLE operator (
            singleton  INTEGER PRIMARY KEY CHECK (singleton = 1),
            id         TEXT NOT NULL,
            name       TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE projects (
            path           TEXT PRIMARY KEY,
            last_opened_at TEXT NOT NULL,
            last_mode      TEXT NOT NULL DEFAULT ''
        )
        """,
        """
        CREATE TABLE preferences (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
    ),
    (
        # A source picked from a list needs a name to be recognised by later,
        # and the protocol says how the endpoint is spoken to. Both were
        # missing when a provider was only ever the one built-in slot.
        "ALTER TABLE providers ADD COLUMN display_name TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE providers ADD COLUMN protocol TEXT NOT NULL DEFAULT "
        "'openai_compatible'",
    ),
    (
        # OAuth grants, one row per account rather than per provider: the same
        # vendor can hold several subscriptions (a personal plan and a team
        # one), and collapsing them onto the provider id would make signing
        # into the second silently evict the first.
        #
        # `authorized_at` is separate from `obtained_at` on purpose. Anthropic
        # expires the whole refresh-token family about thirty days after the
        # interactive login no matter how often it has rotated since, so the
        # moment that matters for warning a user is the original login, and a
        # refresh must not overwrite it.
        """
        CREATE TABLE oauth_credentials (
            provider_id   TEXT NOT NULL,
            account_key   TEXT NOT NULL DEFAULT '',
            access_token  TEXT NOT NULL DEFAULT '',
            refresh_token TEXT NOT NULL DEFAULT '',
            expires_at    TEXT NOT NULL DEFAULT '',
            scope         TEXT NOT NULL DEFAULT '',
            account_label TEXT NOT NULL DEFAULT '',
            account_id    TEXT NOT NULL DEFAULT '',
            org_id        TEXT NOT NULL DEFAULT '',
            plan          TEXT NOT NULL DEFAULT '',
            api_endpoint  TEXT NOT NULL DEFAULT '',
            authorized_at TEXT NOT NULL DEFAULT '',
            obtained_at   TEXT NOT NULL,
            PRIMARY KEY (provider_id, account_key)
        )
        """,
    ),
    (
        # Which signed-in account supplies this endpoint's credential.
        #
        # Empty for an endpoint configured with a static API key, which is
        # still the common case. When set, the stored `api_key` is a cache of
        # the last access token rather than something the user typed, and it
        # is refreshed rather than asked for again.
        "ALTER TABLE providers ADD COLUMN oauth_provider_id TEXT NOT NULL DEFAULT ''",
    ),
)


class UserStore:
    """User-level records in a single SQLite database.

    Opened per operation rather than held: the Agent and the desktop shell are
    separate processes and both read this, so a long-lived connection would
    hold locks across idle time for no benefit.
    """

    def __init__(self, home: Path | None = None) -> None:
        self.home = home or user_home()
        self.path = self.home / "loopforge.db"

    # -- lifecycle ----------------------------------------------------------

    def _ensure_home(self) -> None:
        # 0700: this directory holds credentials, and a permissive default
        # umask would otherwise leave it group- and world-readable.
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self.home.chmod(0o700)
        except OSError:
            # A directory we cannot chmod is still usable; the file mode below
            # is the protection that matters.
            pass

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """An open, migrated connection with foreign keys enforced."""
        self._ensure_home()
        existed = self.path.exists()
        connection = sqlite3.connect(self.path, timeout=10.0)
        try:
            if not existed:
                # Before anything is written, so a credential is never briefly
                # world-readable between creation and chmod.
                self.path.chmod(0o600)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            # WAL so the Agent and the desktop shell can read concurrently
            # without blocking each other.
            connection.execute("PRAGMA journal_mode = WAL")
            self._migrate(connection)
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        current = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if current > SCHEMA_VERSION:
            raise UserStoreError(
                f"This Loopforge store was written by a newer version "
                f"(schema {current}, this build understands {SCHEMA_VERSION}).",
                "USER_STORE_TOO_NEW",
            )
        for version in range(current, SCHEMA_VERSION):
            for statement in MIGRATIONS[version]:
                connection.execute(statement)
            connection.execute(f"PRAGMA user_version = {version + 1}")
        connection.commit()

    # -- providers ----------------------------------------------------------

    def provider(self, provider_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM providers WHERE provider_id = ?", (provider_id,)
            ).fetchone()
        return dict(row) if row else None

    def providers(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM providers ORDER BY provider_id"
            ).fetchall()
        return [dict(row) for row in rows]

    def save_provider(
        self,
        provider_id: str,
        base_url: str,
        api_key: str,
        model: str,
        display_name: str = "",
        protocol: str = "openai_compatible",
        oauth_provider_id: str = "",
    ) -> dict[str, Any]:
        """Record a provider's configuration.

        An empty `api_key` leaves the stored one untouched, so a caller can
        change a base URL or model without having to resend the credential --
        and so a surface can show configuration without ever reading it back.
        """
        identifier = provider_id.strip()
        if not identifier:
            raise UserStoreError("A provider id is required.", "PROVIDER_ID_INVALID")
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT api_key FROM providers WHERE provider_id = ?", (identifier,)
            ).fetchone()
            key = api_key or (existing["api_key"] if existing else "")
            connection.execute(
                """
                INSERT INTO providers
                    (provider_id, base_url, api_key, model, display_name, protocol,
                     oauth_provider_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_id) DO UPDATE SET
                    base_url = excluded.base_url,
                    api_key = excluded.api_key,
                    model = excluded.model,
                    display_name = excluded.display_name,
                    protocol = excluded.protocol,
                    oauth_provider_id = excluded.oauth_provider_id,
                    updated_at = excluded.updated_at
                """,
                (
                    identifier,
                    base_url.strip(),
                    key,
                    model.strip(),
                    display_name.strip(),
                    protocol.strip() or "openai_compatible",
                    oauth_provider_id.strip(),
                    _utc_now(),
                ),
            )
            connection.commit()
        recorded = self.provider(identifier)
        assert recorded is not None
        return recorded

    def forget_provider(self, provider_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM providers WHERE provider_id = ?", (provider_id.strip(),)
            )
            connection.commit()
        return cursor.rowcount > 0

    # -- operator -----------------------------------------------------------

    def operator(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT id, name FROM operator WHERE singleton = 1").fetchone()
        return dict(row) if row else None

    def save_operator(self, identifier: str, name: str) -> dict[str, Any]:
        if not identifier.strip():
            raise UserStoreError("An operator id is required.", "OPERATOR_ID_INVALID")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO operator (singleton, id, name, updated_at)
                VALUES (1, ?, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    id = excluded.id, name = excluded.name, updated_at = excluded.updated_at
                """,
                (identifier.strip(), name.strip(), _utc_now()),
            )
            connection.commit()
        recorded = self.operator()
        assert recorded is not None
        return recorded

    # -- projects -----------------------------------------------------------

    def remember_project(self, path: str, mode: str = "") -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO projects (path, last_opened_at, last_mode) VALUES (?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    last_opened_at = excluded.last_opened_at,
                    last_mode = excluded.last_mode
                """,
                (path, _utc_now(), mode),
            )
            connection.commit()

    def recent_projects(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM projects ORDER BY last_opened_at DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def forget_project(self, path: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM projects WHERE path = ?", (path,))
            connection.commit()
        return cursor.rowcount > 0

    # -- preferences --------------------------------------------------------

    # -- OAuth grants -------------------------------------------------------

    def oauth_grants(self) -> list[dict[str, Any]]:
        """Every signed-in account, newest first."""
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM oauth_credentials ORDER BY obtained_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def oauth_grant(self, provider_id: str, account_key: str = "") -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM oauth_credentials WHERE provider_id = ? AND account_key = ?",
                (provider_id.strip(), account_key.strip()),
            ).fetchone()
        return dict(row) if row else None

    def save_oauth_grant(self, grant: dict[str, Any], account_key: str = "") -> dict[str, Any]:
        """Record a grant, replacing the one for that account.

        Keyed by account rather than by provider: one vendor can hold several
        subscriptions, and collapsing them onto the provider id would make
        signing into the second silently evict the first.
        """
        identifier = str(grant.get("provider_id") or "").strip()
        if not identifier:
            raise UserStoreError("A provider id is required.", "PROVIDER_ID_INVALID")
        row = {
            "provider_id": identifier,
            "account_key": account_key.strip(),
            "access_token": str(grant.get("access_token") or ""),
            "refresh_token": str(grant.get("refresh_token") or ""),
            "expires_at": str(grant.get("expires_at") or ""),
            "scope": str(grant.get("scope") or ""),
            "account_label": str(grant.get("account_label") or ""),
            "account_id": str(grant.get("account_id") or ""),
            "org_id": str(grant.get("org_id") or ""),
            "plan": str(grant.get("plan") or ""),
            "api_endpoint": str(grant.get("api_endpoint") or ""),
            "authorized_at": str(grant.get("authorized_at") or ""),
            "obtained_at": _utc_now(),
        }
        columns = ", ".join(row)
        placeholders = ", ".join("?" for _ in row)
        updates = ", ".join(
            f"{name} = excluded.{name}"
            for name in row
            if name not in ("provider_id", "account_key")
        )
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO oauth_credentials ({columns}) VALUES ({placeholders}) "
                f"ON CONFLICT(provider_id, account_key) DO UPDATE SET {updates}",
                tuple(row.values()),
            )
            connection.commit()
        return row

    def forget_oauth_grant(self, provider_id: str, account_key: str = "") -> bool:
        """Sign an account out locally. True when there was one to remove."""
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM oauth_credentials WHERE provider_id = ? AND account_key = ?",
                (provider_id.strip(), account_key.strip()),
            )
            connection.commit()
            return cursor.rowcount > 0

    def preferences(self) -> dict[str, str]:
        with self.connect() as connection:
            rows = connection.execute("SELECT key, value FROM preferences").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def save_preferences(self, values: dict[str, str]) -> dict[str, str]:
        with self.connect() as connection:
            for key, value in values.items():
                connection.execute(
                    """
                    INSERT INTO preferences (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (str(key), str(value)),
                )
            connection.commit()
        return self.preferences()


class UserStoreError(RuntimeError):
    def __init__(self, message: str, code: str = "USER_STORE_ERROR") -> None:
        super().__init__(message)
        self.code = code
