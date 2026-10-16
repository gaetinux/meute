use assert_cmd::Command;
use predicates::str::starts_with;

#[test]
fn version_flag_prints_name_and_version() {
    Command::cargo_bin("meute")
        .unwrap()
        .arg("--version")
        .assert()
        .success()
        .stdout(starts_with(format!("meute {}", env!("CARGO_PKG_VERSION"))));
}
