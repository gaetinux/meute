use predicates::prelude::*;

#[cfg(test)]
mod support;

use support::*;

#[test]
fn status_blocked_requires_reason_then_shows_it() {
    let tmp = setup_with_task();
    meute(&tmp)
        .args(["task", "status", "1", "blocked"])
        .assert()
        .code(1);
    meute(&tmp)
        .args([
            "task",
            "status",
            "1",
            "blocked",
            "--reason",
            "attente revue",
        ])
        .assert()
        .success()
        .stdout("#1 ✕ Relire la PR · bloquée : attente revue\n");
}

#[test]
fn stale_expected_version_exits_3_with_current_state() {
    let tmp = setup_with_task();
    meute(&tmp)
        .args(["task", "edit", "1", "--title", "A"])
        .assert()
        .success();
    meute(&tmp)
        .args([
            "task",
            "edit",
            "1",
            "--title",
            "B",
            "--expected-version",
            "1",
        ])
        .assert()
        .code(3)
        .stderr(
            predicates::str::contains("modifiée entre-temps (version actuelle : 2)")
                .and(predicates::str::contains("#1 · A")),
        );
}

#[test]
fn snapshot_conflict_message() {
    let tmp = setup_with_task();
    meute(&tmp)
        .args(["task", "edit", "1", "--title", "A"])
        .assert()
        .success();
    let out = meute(&tmp)
        .args([
            "task",
            "edit",
            "1",
            "--title",
            "B",
            "--expected-version",
            "1",
        ])
        .output()
        .unwrap();
    assert_eq!(out.status.code(), Some(3));
    insta::assert_snapshot!(String::from_utf8(out.stderr).unwrap());
}

#[test]
fn rm_without_yes_off_tty_refuses() {
    let tmp = setup_with_task();
    meute(&tmp)
        .args(["task", "rm", "1"])
        .assert()
        .code(1)
        .stderr(predicates::str::contains("relancez avec --yes"));
    meute(&tmp).args(["task", "show", "1"]).assert().success();
    meute(&tmp)
        .args(["task", "rm", "1", "--yes"])
        .assert()
        .success();
    meute(&tmp).args(["task", "show", "1"]).assert().code(4);
}

#[test]
fn note_then_show_lists_it_with_author() {
    let tmp = setup_with_task();
    meute(&tmp)
        .args(["task", "note", "1", "Commencé"])
        .assert()
        .success()
        .stdout("Note ajoutée à #1\n");
    meute(&tmp)
        .args(["task", "show", "1"])
        .assert()
        .success()
        .stdout(predicates::str::contains("user : Commencé"));
}

#[test]
fn edit_due_invalid_token_is_rejected() {
    let tmp = setup_with_task();
    meute(&tmp)
        .args(["task", "edit", "1", "--due", "bientot"])
        .assert()
        .code(1)
        .stderr(predicates::str::contains("échéance invalide : bientot"));
}

#[test]
fn edit_sets_and_clears_due_and_project() {
    let tmp = setup_with_task();
    meute(&tmp)
        .args(["project", "add", "meute"])
        .assert()
        .success();
    meute(&tmp)
        .args([
            "task",
            "edit",
            "1",
            "--project",
            "meute",
            "--due",
            "demain",
            "--priority",
            "high",
        ])
        .assert()
        .success()
        .stdout("#1 · ! Relire la PR @meute · demain\n");
    meute(&tmp)
        .args(["task", "edit", "1", "--project", "none", "--due", "none"])
        .assert()
        .success()
        .stdout("#1 · ! Relire la PR\n");
    meute(&tmp)
        .args(["task", "edit", "1", "--project", "nope"])
        .assert()
        .code(1)
        .stderr(predicates::str::contains("projet inconnu : nope"));
}
