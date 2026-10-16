//! Integration tests for the `repos` table.

mod common;

use std::path::PathBuf;

use common::test_db;
use meute_core::db::Db;
use meute_core::repo::NewRepo;

fn repo(path: &str, name: &str, kind: Option<&str>) -> NewRepo {
    NewRepo {
        path: PathBuf::from(path),
        name: name.into(),
        kind: kind.map(Into::into),
    }
}

#[test]
fn sync_inserts_then_updates_without_deleting() {
    let first: jiff::Timestamp = "2026-10-14T08:30:00Z".parse().unwrap();
    let later: jiff::Timestamp = "2026-10-15T09:00:00Z".parse().unwrap();
    let mut db = Db::open_in_memory().unwrap().with_clock(move || first);
    let initial = db
        .sync_repos(&[repo("/g/a", "a", Some("rust")), repo("/g/b", "b", None)])
        .unwrap();
    assert_eq!(initial.len(), 2);

    let mut db = db.with_clock(move || later);
    let synced = db.sync_repos(&[repo("/g/a", "a2", Some("node"))]).unwrap();
    assert_eq!(synced.len(), 2);
    let a = &synced[0];
    assert_eq!(a.path, PathBuf::from("/g/a"));
    assert_eq!(a.name, "a2");
    assert_eq!(a.kind.as_deref(), Some("node"));
    assert_eq!(a.discovered_at, first);
    assert_eq!(a.id, initial[0].id);
    assert_eq!(synced[1].path, PathBuf::from("/g/b"));
}

#[test]
fn list_is_sorted_by_name_case_insensitively() {
    let mut db = test_db();
    db.sync_repos(&[
        repo("/g/z", "zeta", None),
        repo("/g/b", "Beta", None),
        repo("/g/a", "alpha", None),
    ])
    .unwrap();
    let names: Vec<String> = db
        .list_repos()
        .unwrap()
        .into_iter()
        .map(|r| r.name)
        .collect();
    assert_eq!(names, ["alpha", "Beta", "zeta"]);
}
