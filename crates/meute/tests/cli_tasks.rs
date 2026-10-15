use assert_cmd::Command;
use jiff::civil::date;
use meute_core::actor::{Actor, Author, Channel};
use meute_core::db::Db;
use meute_core::task::{Due, NewTask, Priority, TaskId, TaskPatch, TaskStatus};
use predicates::prelude::*;
use std::time::Duration;

const NOW: &str = "2026-10-14T10:30[Europe/Paris]";

#[cfg(test)]
mod support {
    use super::*;

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
}
use support::*;

#[test]
fn add_then_list_shows_spec_line() {
    let tmp = tempfile::tempdir().unwrap();
    meute(&tmp)
        .args(["project", "add", "meute"])
        .assert()
        .success();
    meute(&tmp)
        .args([
            "task", "add", "Relire", "la", "PR", "@meute", "!", ">demain",
        ])
        .assert()
        .success()
        .stdout("Créée : #1 · ! Relire la PR @meute · demain\n");
    meute(&tmp)
        .args(["task", "list"])
        .assert()
        .success()
        .stdout("#1 · ! Relire la PR @meute · demain\n");
}

#[test]
fn unknown_project_creates_nothing() {
    let tmp = tempfile::tempdir().unwrap();
    meute(&tmp)
        .args(["project", "add", "meute"])
        .assert()
        .success();
    meute(&tmp)
        .args(["task", "add", "x", "@meuet"])
        .assert()
        .code(1)
        .stderr(predicates::str::contains(
            "projet inconnu : meuet (projets : meute)",
        ));
    meute(&tmp)
        .args(["task", "list", "--all", "--json"])
        .assert()
        .success()
        .stdout("[]\n");
}

#[test]
fn dry_run_creates_nothing() {
    let tmp = tempfile::tempdir().unwrap();
    meute(&tmp)
        .args(["task", "add", "--dry-run", "Payer", "!!", ">ven-14h30"])
        .assert()
        .success()
        .stdout(
            predicates::str::contains("Payer")
                .and(predicates::str::contains("!!"))
                .and(predicates::str::contains("ven. 16 oct. 14:30")),
        );
    meute(&tmp)
        .args(["task", "list", "--json"])
        .assert()
        .stdout("[]\n");
}

#[test]
fn show_missing_task_exits_4() {
    let tmp = tempfile::tempdir().unwrap();
    meute(&tmp).args(["task", "show", "42"]).assert().code(4);
}

#[test]
fn first_run_writes_default_config() {
    let tmp = tempfile::tempdir().unwrap();
    meute(&tmp).args(["task", "list"]).assert().success();
    assert!(tmp.path().join("config/meute/config.toml").exists());
}

#[test]
fn list_status_done_includes_done_tasks() {
    let tmp = tempfile::tempdir().unwrap();
    seed_mixed(&tmp);
    meute(&tmp)
        .args(["task", "list", "--status", "done"])
        .assert()
        .success()
        .stdout("#5 ✓ Clore le ticket @meute\n");
    meute(&tmp)
        .args(["task", "list"])
        .assert()
        .success()
        .stdout(predicates::str::contains("Clore le ticket").not());
}

#[test]
fn list_filters_by_project_and_floating() {
    let tmp = tempfile::tempdir().unwrap();
    seed_mixed(&tmp);
    meute(&tmp)
        .args(["task", "list", "--project", "meute", "--all"])
        .assert()
        .success()
        .stdout(
            predicates::str::contains("Déployer")
                .and(predicates::str::contains("Ranger le bureau").not()),
        );
    meute(&tmp)
        .args(["task", "list", "--floating"])
        .assert()
        .success()
        .stdout(
            predicates::str::contains("Ranger le bureau")
                .and(predicates::str::contains("Déployer").not()),
        );
    meute(&tmp)
        .args(["task", "list", "--project", "nope"])
        .assert()
        .code(1)
        .stderr(predicates::str::contains(
            "projet inconnu : nope (projets : meute)",
        ));
    meute(&tmp)
        .args(["task", "list", "--project", "meute", "--floating"])
        .assert()
        .code(2);
}

#[test]
fn invalid_meute_now_names_the_variable() {
    let tmp = tempfile::tempdir().unwrap();
    meute(&tmp)
        .env("MEUTE_NOW", "pas une date")
        .args(["task", "list"])
        .assert()
        .code(1)
        .stderr(
            predicates::str::starts_with("meute : ").and(predicates::str::contains("MEUTE_NOW")),
        );
}

#[test]
fn project_list_prints_one_name_per_line() {
    let tmp = tempfile::tempdir().unwrap();
    meute(&tmp)
        .args(["project", "add", "zeta"])
        .assert()
        .success()
        .stdout("Projet créé : zeta\n");
    meute(&tmp)
        .args(["project", "add", "alpha", "--description", "d"])
        .assert()
        .success();
    meute(&tmp)
        .args(["project", "list"])
        .assert()
        .success()
        .stdout("alpha\nzeta\n");
    meute(&tmp)
        .args(["project", "list", "--json"])
        .assert()
        .success()
        .stdout(predicates::str::contains("\"name\":\"alpha\""));
}

#[test]
fn snapshot_task_list_mixed() {
    let tmp = tempfile::tempdir().unwrap();
    seed_mixed(&tmp);
    let out = meute(&tmp)
        .args(["task", "list", "--all"])
        .output()
        .unwrap();
    assert!(out.status.success());
    insta::assert_snapshot!(String::from_utf8(out.stdout).unwrap());
}

#[test]
fn snapshot_task_show_with_notes() {
    let tmp = tempfile::tempdir().unwrap();
    seed_mixed(&tmp);
    let mut db = open_db(&tmp);
    db.add_note(TaskId(1), "Premier point fait.", &actor())
        .unwrap();
    let claude = Actor {
        author: Author::Claude,
        channel: Channel::Mcp,
        session_id: Some("s1".into()),
    };
    db.add_note(TaskId(1), "Reste la relecture.", &claude)
        .unwrap();
    let out = meute(&tmp).args(["task", "show", "1"]).output().unwrap();
    assert!(out.status.success());
    insta::assert_snapshot!(String::from_utf8(out.stdout).unwrap());
}
