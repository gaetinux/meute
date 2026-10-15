#[cfg(test)]
mod support;

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
