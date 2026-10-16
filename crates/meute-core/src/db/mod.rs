//! SQLite access: connection, pragmas, clock and migrations.

mod migrations;
mod projects;
mod task_notes;
mod task_update;
mod tasks;
pub mod time;

pub use tasks::{ProjectFilter, TaskFilter};

use std::path::Path;
use std::time::Duration;

use jiff::Timestamp;
use rusqlite::Connection;
use rusqlite::types::Value;

use crate::error::{CoreError, Result};

/// Source of the current time, replaceable in tests.
type Clock = Box<dyn Fn() -> Timestamp + Send + Sync>;

/// An open, migrated meute database together with its clock.
pub struct Db {
    conn: Connection,
    clock: Clock,
}

impl Db {
    /// Open (creating the file and its parent directories if needed) the
    /// database at `path`, apply the pragmas, then migrate to the latest schema.
    pub fn open(path: &Path, busy_timeout: Duration) -> Result<Db> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let mut conn = Connection::open(path)?;
        conn.busy_timeout(busy_timeout)?;
        conn.pragma_update(None, "journal_mode", "WAL")?;
        conn.pragma_update(None, "foreign_keys", "ON")?;
        migrations::migrate(&mut conn, Some(path), &migrations::all())?;
        Ok(Db::from_connection(conn))
    }

    /// Open a fresh in-memory database (for tests).
    pub fn open_in_memory() -> Result<Db> {
        let mut conn = Connection::open_in_memory()?;
        conn.pragma_update(None, "foreign_keys", "ON")?;
        migrations::migrate(&mut conn, None, &migrations::all())?;
        Ok(Db::from_connection(conn))
    }

    fn from_connection(conn: Connection) -> Db {
        Db {
            conn,
            clock: Box::new(Timestamp::now),
        }
    }

    /// Replace the clock used to stamp rows (default: [`Timestamp::now`]).
    #[must_use]
    pub fn with_clock(mut self, clock: impl Fn() -> Timestamp + Send + Sync + 'static) -> Db {
        self.clock = Box::new(clock);
        self
    }

    /// Current time according to the database clock.
    pub(crate) fn now(&self) -> Timestamp {
        (self.clock)()
    }

    /// Schema version (`PRAGMA user_version`) of the database.
    pub fn schema_version(&self) -> Result<usize> {
        migrations::current_version(&self.conn, &migrations::all())
    }

    /// Value of the SQLite pragma `name`, as text (e.g. `journal_mode`).
    pub fn pragma_string(&self, name: &str) -> Result<String> {
        let valid = !name.is_empty() && name.bytes().all(|b| b.is_ascii_lowercase() || b == b'_');
        if !valid {
            return Err(CoreError::Invalid(format!(
                "nom de pragma invalide : {name}"
            )));
        }
        let value: Value = self
            .conn
            .query_row(&format!("PRAGMA {name}"), [], |row| row.get(0))?;
        match value {
            Value::Integer(i) => Ok(i.to_string()),
            Value::Real(f) => Ok(f.to_string()),
            Value::Text(s) => Ok(s),
            Value::Null => Ok(String::new()),
            Value::Blob(_) => Err(CoreError::Invalid(format!(
                "le pragma {name} renvoie des données binaires"
            ))),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn custom_clock_is_used() {
        let ts: Timestamp = "2026-01-02T03:04:05Z".parse().unwrap();
        let db = Db::open_in_memory().unwrap().with_clock(move || ts);
        assert_eq!(db.now(), ts);
    }

    #[test]
    fn in_memory_db_is_migrated_with_foreign_keys() {
        let db = Db::open_in_memory().unwrap();
        assert_eq!(db.schema_version().unwrap(), 1);
        assert_eq!(db.pragma_string("foreign_keys").unwrap(), "1");
    }
}
