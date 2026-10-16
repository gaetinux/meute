//! Versioned schema migrations with a backup before upgrading an existing file.

use std::path::{Path, PathBuf};

use rusqlite::Connection;
use rusqlite_migration::{M, Migrations};

use crate::error::{CoreError, Result};

const MIGRATION_1: &str = include_str!("sql/001_init.sql");
const MIGRATION_2: &str = include_str!("sql/002_sessions.sql");

/// All migrations of the application, in order.
pub(super) fn all() -> Migrations<'static> {
    Migrations::new(vec![M::up(MIGRATION_1), M::up(MIGRATION_2)])
}

/// Current schema version of the database (0 when never migrated).
pub(super) fn current_version(conn: &Connection, migrations: &Migrations<'_>) -> Result<usize> {
    let version = migrations
        .current_version(conn)
        .map_err(|e| CoreError::Migration(e.to_string()))?;
    Ok(usize::from(version))
}

/// Path of the backup taken before leaving `version`: `<db file name>.bak-<version>`.
fn backup_path(db_path: &Path, version: usize) -> PathBuf {
    let mut name = db_path.file_name().unwrap_or_default().to_os_string();
    name.push(format!(".bak-{version}"));
    db_path.with_file_name(name)
}

/// Migrate `conn` to the latest version. An existing file database with
/// `0 < version < target` is first saved with `VACUUM INTO`.
pub(super) fn migrate(
    conn: &mut Connection,
    db_path: Option<&Path>,
    migrations: &Migrations<'_>,
) -> Result<()> {
    let version = current_version(conn, migrations)?;
    let pending = migrations
        .pending_migrations(conn)
        .map_err(|e| CoreError::Migration(e.to_string()))?;
    if let Some(path) = db_path {
        if version > 0 && pending > 0 {
            let backup = backup_path(path, version);
            if backup.exists() {
                std::fs::remove_file(&backup)?;
            }
            conn.execute("VACUUM INTO ?1", [backup.to_string_lossy().as_ref()])?;
        }
    }
    migrations
        .to_latest(conn)
        .map_err(|e| CoreError::Migration(e.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn has_table(conn: &Connection, name: &str) -> bool {
        conn.query_row(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?1",
            [name],
            |r| r.get::<_, i64>(0),
        )
        .unwrap()
            > 0
    }

    #[test]
    fn upgrading_an_existing_file_backs_it_up_first() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("meute.db");
        {
            let mut conn = Connection::open(&path).unwrap();
            conn.pragma_update(None, "journal_mode", "WAL").unwrap();
            let v1 = Migrations::new(vec![M::up("CREATE TABLE a(x)")]);
            migrate(&mut conn, Some(&path), &v1).unwrap();
        }
        let mut conn = Connection::open(&path).unwrap();
        conn.pragma_update(None, "journal_mode", "WAL").unwrap();
        let v2 = Migrations::new(vec![M::up("CREATE TABLE a(x)"), M::up("CREATE TABLE b(x)")]);
        migrate(&mut conn, Some(&path), &v2).unwrap();
        assert_eq!(current_version(&conn, &v2).unwrap(), 2);
        assert!(has_table(&conn, "b"));

        let backup = dir.path().join("meute.db.bak-1");
        assert!(backup.exists());
        let saved = Connection::open(&backup).unwrap();
        assert!(has_table(&saved, "a"));
        assert!(!has_table(&saved, "b"));
    }

    #[test]
    fn fresh_file_makes_no_backup() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("meute.db");
        let mut conn = Connection::open(&path).unwrap();
        migrate(&mut conn, Some(&path), &all()).unwrap();
        assert!(!dir.path().join("meute.db.bak-0").exists());
    }
}
