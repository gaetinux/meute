#[cfg(test)]
mod support;

use predicates::prelude::*;
use support::*;

#[test]
fn set_then_get_round_trips() {
    let tmp = tempfile::tempdir().unwrap();
    meute(&tmp)
        .args(["config", "set", "ui.board_width", "72"])
        .assert()
        .success();
    meute(&tmp)
        .args(["config", "get", "ui.board_width"])
        .assert()
        .success()
        .stdout("72\n");
}

#[test]
fn set_unknown_key_exits_1() {
    let tmp = tempfile::tempdir().unwrap();
    meute(&tmp)
        .args(["config", "set", "ui.nope", "1"])
        .assert()
        .code(1);
}

#[test]
fn path_ends_with_config_toml() {
    let tmp = tempfile::tempdir().unwrap();
    meute(&tmp)
        .args(["config", "path"])
        .assert()
        .success()
        .stdout(predicates::str::ends_with("meute/config.toml\n"));
}

#[test]
fn path_works_even_when_config_is_invalid() {
    let tmp = tempfile::tempdir().unwrap();
    let file = tmp.path().join("config/meute/config.toml");
    std::fs::create_dir_all(file.parent().unwrap()).unwrap();
    std::fs::write(&file, "[ui]\nboard_width = = 3\n").unwrap();
    meute(&tmp)
        .args(["config", "path"])
        .assert()
        .success()
        .stdout(predicates::str::ends_with("meute/config.toml\n"));
}

#[test]
fn set_on_invalid_config_reports_path_and_line_and_keeps_file() {
    let tmp = tempfile::tempdir().unwrap();
    let file = tmp.path().join("config/meute/config.toml");
    std::fs::create_dir_all(file.parent().unwrap()).unwrap();
    std::fs::write(&file, "[ui]\nboard_width = = 3\n").unwrap();
    meute(&tmp)
        .args(["config", "set", "ui.board_width", "72"])
        .assert()
        .code(1)
        .stderr(predicates::str::contains("config.toml").and(predicates::str::contains("line 2")));
    assert_eq!(
        std::fs::read_to_string(&file).unwrap(),
        "[ui]\nboard_width = = 3\n"
    );
}
