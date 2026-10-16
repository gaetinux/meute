//! Error mapping and input validation of the database layer, added after a
//! cargo-mutants run.

use std::time::Duration;

mod common;

use common::*;
use meute_core::CoreError;
use meute_core::db::Db;

/// A file database plus a second raw connection used to sabotage its schema.
#[expect(
    clippy::unwrap_used,
    reason = "shared test helper, not itself a #[test] function"
)]
fn file_db() -> (tempfile::TempDir, Db, rusqlite::Connection) {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("meute.db");
    let db = Db::open(&path, Duration::from_secs(5)).unwrap();
    let raw = rusqlite::Connection::open(&path).unwrap();
    (dir, db, raw)
}

#[test]
fn pragma_string_rejects_empty_and_malformed_names() {
    let db = Db::open_in_memory().unwrap();
    for name in ["", "journal-mode", "Journal_Mode", "foreign keys"] {
        let err = db.pragma_string(name).unwrap_err();
        assert!(matches!(err, CoreError::Invalid(_)), "{name:?}: {err:?}");
    }
}

#[test]
fn create_project_only_maps_constraint_violations_to_duplicates() {
    let (_dir, mut db, raw) = file_db();
    raw.execute_batch("ALTER TABLE projects RENAME TO projects_gone;")
        .unwrap();
    let err = db.create_project("x", "").unwrap_err();
    assert!(matches!(err, CoreError::Db(_)), "{err:?}");
}

#[test]
fn create_task_only_maps_foreign_key_violations_to_unknown_project() {
    let (_dir, mut db, raw) = file_db();
    let project = db.create_project("p", "").unwrap();
    raw.execute_batch(
        "CREATE TRIGGER refuse_tasks BEFORE INSERT ON tasks \
         BEGIN SELECT RAISE(ABORT, 'refused'); END;",
    )
    .unwrap();
    let err = db
        .create_task(new_task("t", Some(project.id)), &user())
        .unwrap_err();
    assert!(matches!(err, CoreError::Db(_)), "{err:?}");
}
