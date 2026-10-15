//! Integration tests for opening the database.

use std::time::Duration;

use meute_core::db::Db;

#[test]
fn open_creates_file_with_wal_and_latest_schema() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("sub/meute.db");
    let db = Db::open(&path, Duration::from_millis(5000)).unwrap();
    assert!(path.exists());
    assert_eq!(db.schema_version().unwrap(), 1);
    assert_eq!(db.pragma_string("journal_mode").unwrap(), "wal");
    assert_eq!(db.pragma_string("foreign_keys").unwrap(), "1");
}

#[test]
fn reopening_is_idempotent_and_makes_no_backup() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("meute.db");
    drop(Db::open(&path, Duration::from_secs(5)).unwrap());
    drop(Db::open(&path, Duration::from_secs(5)).unwrap());
    let backups = std::fs::read_dir(dir.path())
        .unwrap()
        .filter(|e| {
            e.as_ref()
                .unwrap()
                .file_name()
                .to_string_lossy()
                .contains(".bak-")
        })
        .count();
    assert_eq!(backups, 0);
}

#[test]
fn pragma_string_rejects_injection() {
    let db = Db::open_in_memory().unwrap();
    assert!(db.pragma_string("user_version; DROP TABLE tasks").is_err());
}
