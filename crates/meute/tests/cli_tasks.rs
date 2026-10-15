use meute_core::actor::{Actor, Author, Channel};
use meute_core::task::TaskId;
use predicates::prelude::*;

#[cfg(test)]
mod support;

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
