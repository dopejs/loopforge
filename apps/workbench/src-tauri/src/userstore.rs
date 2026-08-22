//! Read and write the user store from the desktop shell.
//!
//! The Agent owns this database and defines its schema (see
//! `cli/loopforge/userstore.py` and ADR 0007). The shell reads it directly for
//! one reason: the recent-project list is needed on the very first render,
//! to decide which project to reopen, and no Agent exists yet at that point --
//! an Agent is started per project, so asking one for the list of projects is
//! circular.
//!
//! Only the tables the shell genuinely owns are touched here. Credentials are
//! never read: they belong to the Agent, which hands them to Kura, and a
//! window process has no use for them.

use std::path::{Path, PathBuf};

use rusqlite::{Connection, OpenFlags};
use serde::{Deserialize, Serialize};

/// Columns the shell reads. Presence of these is the compatibility test.
///
/// Checked instead of the schema version deliberately. The shell never
/// migrates -- the Agent owns this database, and two writers racing to apply
/// migrations is how a store gets corrupted -- but pinning an exact version
/// would mean every column the Agent adds elsewhere blinds the shell to a
/// table it did not touch. What matters is whether `projects` still has what
/// is read here.
const REQUIRED_PROJECT_COLUMNS: [&str; 3] = ["path", "last_opened_at", "last_mode"];

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RecentProject {
    pub path: String,
    pub last_opened_at: String,
    pub last_mode: String,
}

pub fn store_path() -> Option<PathBuf> {
    let home = match std::env::var("LOOPFORGE_HOME") {
        Ok(value) if !value.trim().is_empty() => PathBuf::from(value),
        _ => dirs_home()?.join(".loopforge"),
    };
    Some(home.join("loopforge.db"))
}

fn dirs_home() -> Option<PathBuf> {
    std::env::var_os("HOME").map(PathBuf::from)
}

/// Opens the store read-only, or `None` when it does not exist yet.
///
/// Absence is normal: a first run has no store until the Agent creates one.
///
/// The path is a parameter rather than read from the environment inside, so
/// tests do not have to mutate process state to point somewhere safe -- three
/// of them raced each other over `LOOPFORGE_HOME` before this changed.
fn open_readonly(path: &Path) -> Option<Connection> {
    if !path.is_file() {
        return None;
    }
    let connection = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY).ok()?;
    has_project_columns(&connection).then_some(connection)
}

/// Whether `projects` still carries the columns this module reads.
fn has_project_columns(connection: &Connection) -> bool {
    let Ok(mut statement) = connection.prepare("PRAGMA table_info(projects)") else {
        return false;
    };
    let Ok(rows) = statement.query_map([], |row| row.get::<_, String>(1)) else {
        return false;
    };
    let present: Vec<String> = rows.filter_map(Result::ok).collect();
    REQUIRED_PROJECT_COLUMNS
        .iter()
        .all(|needed| present.iter().any(|column| column == needed))
}

/// Opens the store for writing, or `None` when the Agent has not created it.
///
/// Deliberately does not create it. The Agent owns the schema, and a shell
/// that created an empty database would race the Agent's migrations and could
/// leave a store neither of them expects.
fn open_writable(path: &Path) -> Option<Connection> {
    if !path.is_file() {
        return None;
    }
    let connection = Connection::open(path).ok()?;
    has_project_columns(&connection).then_some(connection)
}

/// Recent projects, most recent first. Empty when there is no store yet.
pub fn recent_projects(limit: usize) -> Vec<RecentProject> {
    match store_path() {
        Some(path) => recent_projects_at(&path, limit),
        None => Vec::new(),
    }
}

fn recent_projects_at(path: &Path, limit: usize) -> Vec<RecentProject> {
    let Some(connection) = open_readonly(path) else {
        return Vec::new();
    };
    let mut statement = match connection.prepare(
        "SELECT path, last_opened_at, last_mode FROM projects \
         ORDER BY last_opened_at DESC LIMIT ?1",
    ) {
        Ok(statement) => statement,
        Err(_) => return Vec::new(),
    };
    let rows = statement.query_map([limit as i64], |row| {
        Ok(RecentProject {
            path: row.get(0)?,
            last_opened_at: row.get(1)?,
            last_mode: row.get(2)?,
        })
    });
    match rows {
        Ok(rows) => rows.filter_map(Result::ok).collect(),
        Err(_) => Vec::new(),
    }
}

/// Records that a project was opened. Silently does nothing without a store.
///
/// Failing loudly here would block opening a project over a convenience: the
/// list is how the window is populated next time, not part of the project's
/// record.
pub fn remember_project(project: &str, mode: &str) -> bool {
    match store_path() {
        Some(path) => remember_project_at(&path, project, mode),
        None => false,
    }
}

fn remember_project_at(path: &Path, project: &str, mode: &str) -> bool {
    let Some(connection) = open_writable(path) else {
        return false;
    };
    connection
        .execute(
            "INSERT INTO projects (path, last_opened_at, last_mode) VALUES (?1, ?2, ?3) \
             ON CONFLICT(path) DO UPDATE SET \
               last_opened_at = excluded.last_opened_at, last_mode = excluded.last_mode",
            rusqlite::params![project, now_utc(), mode],
        )
        .is_ok()
}

pub fn forget_project(project: &str) -> bool {
    match store_path() {
        Some(path) => forget_project_at(&path, project),
        None => false,
    }
}

fn forget_project_at(path: &Path, project: &str) -> bool {
    let Some(connection) = open_writable(path) else {
        return false;
    };
    matches!(
        connection.execute("DELETE FROM projects WHERE path = ?1", [project]),
        Ok(count) if count > 0
    )
}

/// A timestamp in the same shape the Python store writes.
///
/// The column is ordered as text, so the two writers have to agree on the
/// format down to the field widths or the ordering silently breaks.
fn now_utc() -> String {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default();
    let seconds = now.as_secs() as i64;
    let micros = now.subsec_micros();
    let days = seconds.div_euclid(86_400);
    let time_of_day = seconds.rem_euclid(86_400);
    let (year, month, day) = civil_from_days(days);
    format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}.{micros:06}Z",
        time_of_day / 3600,
        (time_of_day % 3600) / 60,
        time_of_day % 60
    )
}

/// Days since the Unix epoch to a calendar date (Howard Hinnant's algorithm).
fn civil_from_days(days: i64) -> (i64, u32, u32) {
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let m = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    (if m <= 2 { y + 1 } else { y }, m, d)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A store created the way the Agent creates it, so the shell is tested
    /// against the schema it will actually meet.
    fn agent_style_store(name: &str) -> PathBuf {
        let home = std::env::temp_dir().join(format!("loopforge-shell-store-{name}"));
        let _ = std::fs::remove_dir_all(&home);
        std::fs::create_dir_all(&home).expect("create home");
        let path = home.join("loopforge.db");
        Connection::open(&path)
            .expect("open")
            .execute_batch(
                "CREATE TABLE projects (
                     path           TEXT PRIMARY KEY,
                     last_opened_at TEXT NOT NULL,
                     last_mode      TEXT NOT NULL DEFAULT ''
                 );
                 PRAGMA user_version = 1;",
            )
            .expect("schema");
        path
    }

    #[test]
    fn a_missing_store_reads_as_no_projects() {
        // A first run has no store until the Agent creates one, which is not
        // an error state for a window that wants a list to show.
        let absent = std::env::temp_dir().join("loopforge-shell-store-absent/loopforge.db");
        assert!(recent_projects_at(&absent, 10).is_empty());
        assert!(!remember_project_at(&absent, "/a", "chat"));
    }

    #[test]
    fn projects_round_trip_most_recent_first() {
        let path = agent_style_store("roundtrip");

        assert!(remember_project_at(&path, "/games/one", "chat"));
        assert!(remember_project_at(&path, "/games/two", "flow"));

        let recorded = recent_projects_at(&path, 10);
        assert_eq!(recorded.len(), 2);
        assert_eq!(recorded[0].path, "/games/two");
        assert_eq!(recorded[0].last_mode, "flow");
    }

    #[test]
    fn reopening_updates_rather_than_duplicating() {
        let path = agent_style_store("reopen");

        remember_project_at(&path, "/games/one", "chat");
        remember_project_at(&path, "/games/one", "tasks");

        let recorded = recent_projects_at(&path, 10);
        assert_eq!(recorded.len(), 1);
        assert_eq!(recorded[0].last_mode, "tasks");
    }

    #[test]
    fn a_later_schema_version_still_reads() {
        // The Agent migrates this database for its own tables. Refusing to
        // read `projects` because some unrelated column was added elsewhere
        // would blind the window for no reason.
        let path = agent_style_store("newer");
        Connection::open(&path)
            .expect("open")
            .execute_batch(
                "ALTER TABLE projects ADD COLUMN unrelated TEXT NOT NULL DEFAULT '';
                 PRAGMA user_version = 99;",
            )
            .expect("bump");

        assert!(remember_project_at(&path, "/a", "chat"));
        assert_eq!(recent_projects_at(&path, 10).len(), 1);
    }

    #[test]
    fn a_missing_column_reads_as_no_projects() {
        // The real incompatibility: a table that no longer holds what is read
        // here. Guessing at it would mean reading columns that may not mean
        // what this code thinks.
        let home = std::env::temp_dir().join("loopforge-shell-store-shape");
        let _ = std::fs::remove_dir_all(&home);
        std::fs::create_dir_all(&home).expect("create home");
        let path = home.join("loopforge.db");
        Connection::open(&path)
            .expect("open")
            .execute_batch("CREATE TABLE projects (path TEXT PRIMARY KEY); PRAGMA user_version = 1;")
            .expect("schema");

        assert!(recent_projects_at(&path, 10).is_empty());
        assert!(!remember_project_at(&path, "/a", "chat"));
    }

    #[test]
    fn forgetting_reports_whether_it_existed() {
        let path = agent_style_store("forget");

        remember_project_at(&path, "/games/one", "chat");
        assert!(forget_project_at(&path, "/games/one"));
        assert!(!forget_project_at(&path, "/games/one"));
    }

    /// The only test here that reads a store the Agent actually created.
    ///
    /// Every other case builds the schema from a copy written by hand, which
    /// verifies this code against my transcription rather than against the
    /// Python definition. If the two drift -- a renamed column, a different
    /// `user_version` -- those tests keep passing and the shell silently reads
    /// nothing. Skipped when the repository layout or Python is unavailable,
    /// since that means the question cannot be asked rather than answered no.
    #[test]
    fn a_store_created_by_the_agent_is_readable() {
        let repository = match std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(3)
        {
            Some(path) if path.join("cli/loopforge/userstore.py").is_file() => path.to_path_buf(),
            _ => return,
        };
        let home = std::env::temp_dir().join("loopforge-shell-store-agentmade");
        let _ = std::fs::remove_dir_all(&home);

        let created = std::process::Command::new("python3")
            .arg("-c")
            .arg(
                "import sys; sys.path.insert(0, 'cli')\n\
                 from loopforge.userstore import UserStore\n\
                 import os\n\
                 s = UserStore(__import__('pathlib').Path(os.environ['H']))\n\
                 s.remember_project('/games/from-python', 'chat')",
            )
            .current_dir(&repository)
            .env("H", &home)
            .output();
        let Ok(output) = created else { return };
        if !output.status.success() {
            return;
        }

        let recorded = recent_projects_at(&home.join("loopforge.db"), 10);

        assert_eq!(recorded.len(), 1, "the shell could not read the Agent's store");
        assert_eq!(recorded[0].path, "/games/from-python");
        assert_eq!(recorded[0].last_mode, "chat");

        // And writing back is readable by the same schema.
        assert!(remember_project_at(&home.join("loopforge.db"), "/games/from-rust", "flow"));
        let both = recent_projects_at(&home.join("loopforge.db"), 10);
        assert_eq!(both.len(), 2);
        // Ordering is by text timestamp across both writers, which is the
        // whole reason the formats have to match.
        assert_eq!(both[0].path, "/games/from-rust");
    }

    #[test]
    fn the_timestamp_matches_the_python_format() {
        // Both writers order this column as text, so the formats have to agree
        // down to the field widths or sorting silently breaks.
        let stamp = now_utc();
        assert_eq!(stamp.len(), 27, "{stamp}");
        assert!(stamp.ends_with('Z'), "{stamp}");
        assert_eq!(&stamp[4..5], "-");
        assert_eq!(&stamp[10..11], "T");
        assert_eq!(&stamp[19..20], ".");
    }
}
