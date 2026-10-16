//! Integration tests for the `sessions` table.

mod common;

use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use jiff::Timestamp;
use meute_core::CoreError;
use meute_core::db::Db;
use meute_core::repo::RepoId;
use meute_core::session::{AgentKind, NewSession, SessionFilter, SessionId, SessionState};
use rusqlite_migration::{M, Migrations};

fn bash_session(id: SessionId, title: &str) -> NewSession {
    NewSession {
        id,
        agent: AgentKind::Bash,
        title: title.into(),
        cwd: PathBuf::from("/tmp/work"),
        project_id: None,
        repo_id: None,
        task_id: None,
        state: SessionState::Running,
    }
}

#[test]
fn create_then_get_round_trips_every_field() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("meute.db");
    let mut db = common::clocked(Db::open(&path, Duration::from_secs(5)).unwrap());
    let project = db.create_project("meute", "").unwrap();
    let task = db
        .create_task(common::new_task("t", Some(project.id)), &common::user())
        .unwrap();
    rusqlite::Connection::open(&path)
        .unwrap()
        .execute(
            "INSERT INTO repos (path, name, discovered_at) VALUES ('/r', 'r', '2026-01-01T00:00:00.000000Z')",
            [],
        )
        .unwrap();
    let new = NewSession {
        id: SessionId::new(),
        agent: AgentKind::Claude,
        title: "  travail  ".into(),
        cwd: PathBuf::from("/home/u/repo"),
        project_id: Some(project.id),
        repo_id: Some(RepoId(1)),
        task_id: Some(task.id),
        state: SessionState::Idle,
    };
    let created = db.create_session(new).unwrap();
    let now: Timestamp = "2026-10-14T08:30:00Z".parse().unwrap();
    assert_eq!(created.agent, AgentKind::Claude);
    assert_eq!(created.title, "travail");
    assert_eq!(created.project_id, Some(project.id));
    assert_eq!(created.repo_id, Some(RepoId(1)));
    assert_eq!(created.task_id, Some(task.id));
    assert_eq!(created.cwd, PathBuf::from("/home/u/repo"));
    assert_eq!(created.state, SessionState::Idle);
    assert_eq!(created.created_at, now);
    assert_eq!(created.last_activity_at, now);
    assert_eq!(created.ended_at, None);
    assert_eq!(db.get_session(created.id).unwrap(), created);
}

#[test]
fn create_rejects_blank_title_and_get_unknown_is_not_found() {
    let mut db = common::test_db();
    let err = db
        .create_session(bash_session(SessionId::new(), "   "))
        .unwrap_err();
    assert!(matches!(err, CoreError::Invalid(m) if m == "le titre ne peut pas être vide"));
    let id = SessionId::new();
    assert!(matches!(
        db.get_session(id),
        Err(CoreError::NotFound {
            entity: "session",
            ..
        })
    ));
}

#[test]
fn list_excludes_ended_unless_asked() {
    let mut db = common::test_db();
    let live = db
        .create_session(bash_session(SessionId::new(), "vivante"))
        .unwrap();
    let dead = db
        .create_session(bash_session(SessionId::new(), "finie"))
        .unwrap();
    db.set_session_state(dead.id, SessionState::Exited { code: Some(0) })
        .unwrap();
    let live_only = db.list_sessions(SessionFilter::default()).unwrap();
    assert_eq!(live_only.len(), 1);
    assert_eq!(live_only[0].id, live.id);
    let all = db
        .list_sessions(SessionFilter {
            include_ended: true,
        })
        .unwrap();
    assert_eq!(all.len(), 2);
}

#[test]
fn ended_at_is_set_once_when_leaving_live_states() {
    let clock = Arc::new(Mutex::new(
        "2026-10-14T08:00:00Z".parse::<Timestamp>().unwrap(),
    ));
    let shared = Arc::clone(&clock);
    let mut db = Db::open_in_memory()
        .unwrap()
        .with_clock(move || *shared.lock().unwrap());
    let s = db
        .create_session(bash_session(SessionId::new(), "s"))
        .unwrap();
    let t1: Timestamp = "2026-10-14T09:00:00Z".parse().unwrap();
    let t2: Timestamp = "2026-10-14T10:00:00Z".parse().unwrap();
    *clock.lock().unwrap() = t1;
    let exited = db
        .set_session_state(s.id, SessionState::Exited { code: Some(2) })
        .unwrap();
    assert_eq!(exited.state, SessionState::Exited { code: Some(2) });
    assert_eq!(exited.ended_at, Some(t1));
    assert_eq!(exited.last_activity_at, t1);
    *clock.lock().unwrap() = t2;
    let unreachable = db
        .set_session_state(s.id, SessionState::Unreachable)
        .unwrap();
    assert_eq!(unreachable.ended_at, Some(t1));
    assert_eq!(unreachable.last_activity_at, t2);
}

#[test]
fn find_session_by_unique_prefix_ambiguous_and_short() {
    let mut db = common::test_db();
    let a = SessionId::parse("aaaa1111-0000-4000-8000-000000000001").unwrap();
    let b = SessionId::parse("aaaa2222-0000-4000-8000-000000000002").unwrap();
    db.create_session(bash_session(a, "a")).unwrap();
    db.create_session(bash_session(b, "b")).unwrap();
    assert_eq!(db.find_session("aaaa1").unwrap().id, a);
    assert_eq!(db.find_session(&b.to_string()).unwrap().id, b);
    assert!(matches!(
        db.find_session("aaaa"),
        Err(CoreError::Invalid(m)) if m == "identifiant de session ambigu : aaaa"
    ));
    assert!(matches!(
        db.find_session("aaa"),
        Err(CoreError::NotFound {
            entity: "session",
            ..
        })
    ));
    assert!(matches!(
        db.find_session("ffff"),
        Err(CoreError::NotFound {
            entity: "session",
            ..
        })
    ));
}

#[test]
fn data_version_changes_after_a_write_from_another_connection() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("meute.db");
    let reader = Db::open(&path, Duration::from_secs(5)).unwrap();
    let mut writer = Db::open(&path, Duration::from_secs(5)).unwrap();
    let before = reader.data_version().unwrap();
    writer
        .create_session(bash_session(SessionId::new(), "s"))
        .unwrap();
    assert_ne!(reader.data_version().unwrap(), before);
}

#[test]
fn migrating_a_v1_file_keeps_tasks_and_backs_it_up() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("meute.db");
    {
        let mut conn = rusqlite::Connection::open(&path).unwrap();
        conn.pragma_update(None, "journal_mode", "WAL").unwrap();
        let v1 = Migrations::new(vec![M::up(include_str!("../src/db/sql/001_init.sql"))]);
        v1.to_latest(&mut conn).unwrap();
        conn.execute(
            "INSERT INTO tasks (title, description, status, priority, version, created_at, updated_at) \
             VALUES ('ancienne', '', 'todo', 'normal', 1, '2026-01-01T00:00:00.000000Z', '2026-01-01T00:00:00.000000Z')",
            [],
        )
        .unwrap();
    }
    let db = Db::open(&path, Duration::from_secs(5)).unwrap();
    assert_eq!(db.schema_version().unwrap(), 2);
    let tasks = db
        .list_tasks(&meute_core::db::TaskFilter::default())
        .unwrap();
    assert_eq!(tasks.len(), 1);
    assert_eq!(tasks[0].title, "ancienne");
    assert!(dir.path().join("meute.db.bak-1").exists());
}
