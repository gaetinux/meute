#[cfg(test)]
mod support;

use support::*;

#[test]
fn io_error_cause_is_printed_exactly_once() {
    let tmp = tempfile::tempdir().unwrap();
    let blocker = tmp.path().join("not-a-dir");
    std::fs::write(&blocker, "").unwrap();
    let out = meute(&tmp)
        .env("XDG_DATA_HOME", &blocker)
        .args(["task", "list"])
        .assert()
        .code(1)
        .get_output()
        .stderr
        .clone();
    let stderr = String::from_utf8(out).unwrap();
    assert_eq!(stderr.matches("Not a directory").count(), 1, "{stderr}");
    assert!(
        stderr.starts_with("meute : erreur d'entrée/sortie : "),
        "{stderr}"
    );
}
