//! Integration tests for projects and task creation / reading.

use std::time::Duration;

use meute_core::CoreError;
use meute_core::actor::{Actor, Author, Channel};
use meute_core::db::{Db, ProjectFilter, TaskFilter};
use meute_core::project::ProjectId;
use meute_core::task::{NewTask, Priority, TaskId, TaskStatus};

#[expect(
    clippy::unwrap_used,
    reason = "shared test helper, not itself a #[test] function"
)]
fn test_db() -> Db {
    Db::open_in_memory()
        .unwrap()
        .with_clock(|| "2026-10-14T08:30:00Z".parse().unwrap())
}

fn user() -> Actor {
    Actor {
        author: Author::User,
        channel: Channel::Cli,
        session_id: None,
    }
}

fn new_task(title: &str, project_id: Option<ProjectId>) -> NewTask {
    NewTask {
        title: title.into(),
        description: String::new(),
        priority: Priority::Normal,
        due: None,
        project_id,
    }
}

#[test]
fn create_and_get_task_with_project() {
    let mut db = test_db();
    let p = db.create_project("meute", "").unwrap();
    let t = db
        .create_task(
            NewTask {
                title: "Écrire le plan".into(),
                description: String::new(),
                priority: Priority::High,
                due: None,
                project_id: Some(p.id),
            },
            &user(),
        )
        .unwrap();
    assert_eq!((t.version, t.status.clone()), (1, TaskStatus::Todo));
    assert_eq!(t.project.as_ref().map(|r| r.name.as_str()), Some("meute"));
    assert_eq!(db.get_task(t.id).unwrap(), t);
    let h = db.history(t.id).unwrap();
    assert_eq!(h.len(), 1);
    assert_eq!(
        (h[0].field.as_str(), h[0].author, h[0].channel),
        ("created", Author::User, Channel::Cli)
    );
}

#[test]
fn project_names_are_case_insensitive_and_unique() {
    let mut db = test_db();
    db.create_project("Meute", "").unwrap();
    assert!(db.project_by_name("meute").unwrap().is_some());
    assert!(matches!(
        db.create_project("MEUTE", ""),
        Err(CoreError::Invalid(_))
    ));
    assert!(matches!(
        db.create_project("  ", ""),
        Err(CoreError::Invalid(_))
    ));
}

#[test]
fn list_projects_is_sorted_by_name() {
    let mut db = test_db();
    db.create_project("zeta", "").unwrap();
    db.create_project("Alpha", "desc").unwrap();
    let names: Vec<String> = db
        .list_projects()
        .unwrap()
        .into_iter()
        .map(|p| p.name)
        .collect();
    assert_eq!(names, ["Alpha", "zeta"]);
}

#[test]
fn list_filters_done_floating_and_project() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("meute.db");
    let mut db = Db::open(&path, Duration::from_secs(5))
        .unwrap()
        .with_clock(|| "2026-10-14T08:30:00Z".parse().unwrap());
    let a = db.create_project("A", "").unwrap();
    let t1 = db.create_task(new_task("t1", Some(a.id)), &user()).unwrap();
    let t2 = db.create_task(new_task("t2", None), &user()).unwrap();
    let t3 = db.create_task(new_task("t3", Some(a.id)), &user()).unwrap();
    assert_eq!((t1.id, t2.id, t3.id), (TaskId(1), TaskId(2), TaskId(3)));

    // No update API yet: mark t3 done through a second plain connection.
    let other = rusqlite::Connection::open(&path).unwrap();
    other
        .execute(
            "UPDATE tasks SET status='done', completed_at='2026-10-14T09:00:00Z' WHERE id=3",
            [],
        )
        .unwrap();

    let ids = |filter: &TaskFilter| -> Vec<i64> {
        db.list_tasks(filter)
            .unwrap()
            .into_iter()
            .map(|t| t.id.0)
            .collect()
    };
    assert_eq!(ids(&TaskFilter::default()), [1, 2]);
    assert_eq!(
        ids(&TaskFilter {
            project: ProjectFilter::Floating,
            ..TaskFilter::default()
        }),
        [2]
    );
    assert_eq!(
        ids(&TaskFilter {
            include_done: true,
            project: ProjectFilter::Project(a.id),
            ..TaskFilter::default()
        }),
        [1, 3]
    );
    assert_eq!(
        ids(&TaskFilter {
            include_done: true,
            status: Some("done"),
            ..TaskFilter::default()
        }),
        [3]
    );
}

#[test]
fn get_missing_task_is_not_found() {
    let db = test_db();
    assert!(matches!(
        db.get_task(TaskId(99)),
        Err(CoreError::NotFound { .. })
    ));
}
