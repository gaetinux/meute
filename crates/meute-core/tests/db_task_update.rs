//! Integration tests for versioned updates, notes and deletion.

use std::time::Duration;

use meute_core::CoreError;
use meute_core::actor::{Actor, Author, Channel};
use meute_core::db::Db;
use meute_core::project::ProjectId;
use meute_core::task::{Due, NewTask, Priority, Task, TaskPatch, TaskStatus};

#[expect(
    clippy::unwrap_used,
    reason = "shared test helper, not itself a #[test] function"
)]
fn clocked(db: Db) -> Db {
    db.with_clock(|| "2026-10-14T08:30:00Z".parse().unwrap())
}

#[expect(
    clippy::unwrap_used,
    reason = "shared test helper, not itself a #[test] function"
)]
fn test_db() -> Db {
    clocked(Db::open_in_memory().unwrap())
}

fn user() -> Actor {
    Actor {
        author: Author::User,
        channel: Channel::Cli,
        session_id: None,
    }
}

fn claude() -> Actor {
    Actor {
        author: Author::Claude,
        channel: Channel::Mcp,
        session_id: Some("s-1".into()),
    }
}

fn new_task(title: &str) -> NewTask {
    NewTask {
        title: title.into(),
        description: String::new(),
        priority: Priority::Normal,
        due: None,
        project_id: None,
    }
}

#[expect(
    clippy::unwrap_used,
    reason = "shared test helper, not itself a #[test] function"
)]
fn db_with_task() -> (Db, Task) {
    let mut db = test_db();
    let t = db.create_task(new_task("Relire la PR"), &user()).unwrap();
    (db, t)
}

fn title_patch(title: &str) -> TaskPatch {
    TaskPatch {
        title: Some(title.into()),
        ..Default::default()
    }
}

#[test]
fn update_bumps_version_once_and_logs_each_field() {
    let (mut db, t) = db_with_task();
    let t2 = db
        .update_task(
            t.id,
            1,
            TaskPatch {
                title: Some("Nouveau".into()),
                priority: Some(Priority::Urgent),
                ..Default::default()
            },
            &user(),
        )
        .unwrap();
    assert_eq!(t2.version, 2);
    let fields: Vec<_> = db
        .history(t.id)
        .unwrap()
        .into_iter()
        .map(|e| e.field)
        .collect();
    assert_eq!(fields, ["created", "title", "priority"]);
}

#[test]
fn event_values_use_ids_text_and_project_name() {
    let (mut db, t) = db_with_task();
    let p = db.create_project("meute", "").unwrap();
    let date: jiff::civil::Date = "2026-11-01".parse().unwrap();
    db.update_task(
        t.id,
        1,
        TaskPatch {
            status: Some(TaskStatus::InProgress),
            due: Some(Some(Due::Date(date))),
            project_id: Some(Some(p.id)),
            ..Default::default()
        },
        &claude(),
    )
    .unwrap();
    let h = db.history(t.id).unwrap();
    let pairs: Vec<_> = h[1..]
        .iter()
        .map(|e| {
            (
                e.field.as_str(),
                e.old_value.as_deref(),
                e.new_value.as_deref(),
            )
        })
        .collect();
    assert_eq!(
        pairs,
        [
            ("status", Some("todo"), Some("in_progress")),
            ("due", None, Some("2026-11-01")),
            ("project", None, Some("meute")),
        ]
    );
    assert_eq!(h[1].author, Author::Claude);
    assert_eq!(h[1].session_id.as_deref(), Some("s-1"));
}

#[test]
fn stale_version_is_rejected_with_current_state_and_no_event() {
    let (mut db, t) = db_with_task();
    db.update_task(t.id, 1, title_patch("A"), &user()).unwrap();
    let err = db
        .update_task(t.id, 1, title_patch("B"), &claude())
        .unwrap_err();
    let CoreError::Conflict { current } = err else {
        panic!("expected Conflict, got {err:?}");
    };
    assert_eq!(current.title, "A");
    assert_eq!(current.version, 2);
    assert_eq!(db.history(t.id).unwrap().len(), 2);
}

#[test]
fn noop_patch_changes_nothing() {
    let (mut db, t) = db_with_task();
    let same = db
        .update_task(t.id, 1, title_patch(&t.title), &user())
        .unwrap();
    assert_eq!(same.version, 1);
    assert_eq!(db.history(t.id).unwrap().len(), 1);
}

#[test]
fn done_sets_and_clears_completed_at() {
    let (mut db, t) = db_with_task();
    let d = db
        .update_task(
            t.id,
            1,
            TaskPatch {
                status: Some(TaskStatus::Done),
                ..Default::default()
            },
            &user(),
        )
        .unwrap();
    assert!(d.completed_at.is_some());
    let r = db
        .update_task(
            t.id,
            2,
            TaskPatch {
                status: Some(TaskStatus::Review),
                ..Default::default()
            },
            &user(),
        )
        .unwrap();
    assert!(r.completed_at.is_none());
}

#[test]
fn blank_blocked_reason_is_rejected_and_nothing_written() {
    let (mut db, t) = db_with_task();
    for reason in ["", "  "] {
        let patch = TaskPatch {
            status: Some(TaskStatus::Blocked {
                reason: reason.into(),
            }),
            ..Default::default()
        };
        assert!(matches!(
            db.update_task(t.id, 1, patch, &user()),
            Err(CoreError::Invalid(_))
        ));
    }
    assert_eq!(db.get_task(t.id).unwrap(), t);
    assert_eq!(db.history(t.id).unwrap().len(), 1);
}

#[test]
fn blocked_with_reason_round_trips() {
    let (mut db, t) = db_with_task();
    let patch = TaskPatch {
        status: Some(TaskStatus::Blocked {
            reason: "attend la CI".into(),
        }),
        ..Default::default()
    };
    let b = db.update_task(t.id, 1, patch, &user()).unwrap();
    assert_eq!(
        b.status,
        TaskStatus::Blocked {
            reason: "attend la CI".into()
        }
    );
}

#[test]
fn patch_with_unknown_project_is_not_found_and_nothing_written() {
    let (mut db, t) = db_with_task();
    let patch = TaskPatch {
        project_id: Some(Some(ProjectId(42))),
        ..Default::default()
    };
    let err = db.update_task(t.id, 1, patch, &user()).unwrap_err();
    assert!(
        matches!(
            err,
            CoreError::NotFound {
                entity: "projet",
                ..
            }
        ),
        "{err:?}"
    );
    assert_eq!(db.get_task(t.id).unwrap().version, 1);
    assert_eq!(db.history(t.id).unwrap().len(), 1);
}

#[test]
fn update_missing_task_is_not_found() {
    let mut db = test_db();
    let err = db
        .update_task(meute_core::task::TaskId(9), 1, title_patch("x"), &user())
        .unwrap_err();
    assert!(matches!(err, CoreError::NotFound { .. }));
}

#[test]
fn two_connections_same_version_second_conflicts() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("meute.db");
    let mut a = clocked(Db::open(&path, Duration::from_secs(5)).unwrap());
    let mut b = clocked(Db::open(&path, Duration::from_secs(5)).unwrap());
    let t = a.create_task(new_task("Partagée"), &user()).unwrap();
    let first = a
        .update_task(t.id, 1, title_patch("De A"), &user())
        .unwrap();
    assert_eq!(first.version, 2);
    let err = b
        .update_task(t.id, 1, title_patch("De B"), &claude())
        .unwrap_err();
    let CoreError::Conflict { current } = err else {
        panic!("expected Conflict, got {err:?}");
    };
    assert_eq!(current.title, "De A");
    assert_eq!(a.get_task(t.id).unwrap().version, 2);
    assert_eq!(a.history(t.id).unwrap().len(), 2);
}

#[test]
fn notes_do_not_bump_version_and_keep_author() {
    let (mut db, t) = db_with_task();
    db.add_note(t.id, "Avancé sur la partie SQL", &claude())
        .unwrap();
    assert_eq!(db.get_task(t.id).unwrap().version, 1);
    let n = db.notes(t.id).unwrap();
    assert_eq!(
        (n.len(), n[0].author, n[0].channel),
        (1, Author::Claude, Channel::Mcp)
    );
    assert!(matches!(
        db.add_note(t.id, "  ", &user()),
        Err(CoreError::Invalid(_))
    ));
    assert!(matches!(
        db.add_note(meute_core::task::TaskId(9), "x", &user()),
        Err(CoreError::NotFound { .. })
    ));
}

#[test]
fn delete_checks_version_and_keeps_history() {
    let (mut db, t) = db_with_task();
    db.add_note(t.id, "n", &user()).unwrap();
    assert!(matches!(
        db.delete_task(t.id, 7, &user()),
        Err(CoreError::Conflict { .. })
    ));
    db.delete_task(t.id, 1, &user()).unwrap();
    assert!(matches!(db.get_task(t.id), Err(CoreError::NotFound { .. })));
    let last = db.history(t.id).unwrap().pop().unwrap();
    assert_eq!(
        (last.field.as_str(), last.old_value.as_deref()),
        ("deleted", Some("Relire la PR"))
    );
    assert!(db.notes(t.id).unwrap().is_empty());
}
