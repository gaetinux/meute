#![allow(dead_code, reason = "each test crate uses a subset of the helpers")]
use assert_cmd::Command;
use jiff::civil::date;
use meute_core::actor::{Actor, Author, Channel};
use meute_core::db::Db;
use meute_core::task::{Due, NewTask, Priority, TaskId, TaskPatch, TaskStatus};
use std::time::Duration;

pub const NOW: &str = "2026-10-14T10:30[Europe/Paris]";

pub fn meute(tmp: &tempfile::TempDir) -> Command {
    let mut cmd = Command::cargo_bin("meute").unwrap();
    cmd.env("XDG_CONFIG_HOME", tmp.path().join("config"))
        .env("XDG_DATA_HOME", tmp.path().join("data"))
        .env("XDG_STATE_HOME", tmp.path().join("state"))
        .env("MEUTE_NOW", NOW)
        .env_remove("MEUTE_SESSION");
    cmd
}

pub fn actor() -> Actor {
    Actor {
        author: Author::User,
        channel: Channel::Cli,
        session_id: None,
    }
}

/// Opens the database the CLI created, with a clock fixed on the CLI's `now`.
pub fn open_db(tmp: &tempfile::TempDir) -> Db {
    meute(tmp).args(["task", "list"]).assert().success();
    let ts: jiff::Timestamp = "2026-10-14T08:30:00Z".parse().unwrap();
    Db::open(
        &tmp.path().join("data/meute/meute.db"),
        Duration::from_millis(5000),
    )
    .unwrap()
    .with_clock(move || ts)
}

pub fn new_task(
    title: &str,
    priority: Priority,
    due: Option<Due>,
    project: Option<i64>,
) -> NewTask {
    NewTask {
        title: title.to_owned(),
        description: String::new(),
        priority,
        due,
        project_id: project.map(meute_core::project::ProjectId),
    }
}

/// One task per status and priority, with and without project, various due dates.
pub fn seed_mixed(tmp: &tempfile::TempDir) {
    let mut db = open_db(tmp);
    let project = db.create_project("meute", "").unwrap();
    let p = Some(project.id.0);
    let d = |m, day| Some(Due::Date(date(2026, m, day)));
    let at_today: jiff::Timestamp = "2026-10-14T13:00:00Z".parse().unwrap();
    let rows = [
        new_task("Ranger le bureau", Priority::Normal, None, None),
        new_task("Écrire le guide", Priority::High, d(10, 15), p),
        new_task("Déployer", Priority::Urgent, d(10, 14), p),
        new_task("Relire la PR", Priority::Normal, d(10, 12), None),
        new_task("Clore le ticket", Priority::Low, None, p),
        new_task("Préparer la démo", Priority::Normal, d(10, 21), p),
        new_task(
            "Appeler Marie",
            Priority::High,
            Some(Due::At(at_today)),
            None,
        ),
        new_task("Payer la facture", Priority::Normal, d(10, 10), None),
    ];
    for row in rows {
        db.create_task(row, &actor()).unwrap();
    }
    let statuses = [
        (2, TaskStatus::InProgress),
        (
            3,
            TaskStatus::Blocked {
                reason: "attend la CI".into(),
            },
        ),
        (4, TaskStatus::Review),
        (5, TaskStatus::Done),
    ];
    for (id, status) in statuses {
        let patch = TaskPatch {
            status: Some(status),
            ..TaskPatch::default()
        };
        db.update_task(TaskId(id), 1, patch, &actor()).unwrap();
    }
}

/// Fresh sandbox holding task #1 « Relire la PR » (todo, normal, no project, no due).
pub fn setup_with_task() -> tempfile::TempDir {
    let tmp = tempfile::tempdir().unwrap();
    meute(&tmp)
        .args(["task", "add", "Relire", "la", "PR"])
        .assert()
        .success();
    tmp
}
