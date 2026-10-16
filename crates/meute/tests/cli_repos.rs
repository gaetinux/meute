//! End-to-end tests of `meute repo list`.
#![expect(
    clippy::unwrap_used,
    reason = "test helpers sit outside #[test] fns, where clippy.toml does not allow unwrap"
)]

#[cfg(test)]
mod support;

use std::fs;
use std::path::Path;

use support::meute;

/// Sandbox with `<tmp>/git/api` (Cargo.toml) and `<tmp>/git/front` (package.json),
/// configured as the only repository root. Returns the canonical sandbox path.
fn setup() -> (tempfile::TempDir, std::path::PathBuf) {
    let tmp = tempfile::tempdir().unwrap();
    let home = tmp.path().canonicalize().unwrap();
    for (name, marker) in [("api", "Cargo.toml"), ("front", "package.json")] {
        let dir = home.join("git").join(name);
        fs::create_dir_all(dir.join(".git")).unwrap();
        fs::write(dir.join(marker), "").unwrap();
    }
    let roots = format!("[\"{}\"]", home.join("git").display());
    meute(&tmp)
        .args(["config", "set", "repos.roots", &roots])
        .assert()
        .success();
    (tmp, home)
}

fn list(tmp: &tempfile::TempDir, home: &Path, extra: &[&str]) -> String {
    let out = meute(tmp)
        .env("HOME", home)
        .args(["repo", "list"])
        .args(extra)
        .assert()
        .success();
    String::from_utf8(out.get_output().stdout.clone()).unwrap()
}

#[test]
fn repo_list_scans_configured_roots() {
    let (tmp, home) = setup();
    assert_eq!(
        list(&tmp, &home, &[]),
        "api  rust  ~/git/api\nfront  node  ~/git/front\n"
    );
}

#[test]
fn repo_list_json_is_an_array_of_repos() {
    let (tmp, home) = setup();
    let value: serde_json::Value = serde_json::from_str(&list(&tmp, &home, &["--json"])).unwrap();
    let array = value.as_array().unwrap();
    assert_eq!(array.len(), 2);
    assert_eq!(array[0]["name"], "api");
    assert_eq!(array[0]["kind"], "rust");
    assert_eq!(array[1]["name"], "front");
    assert_eq!(array[1]["kind"], "node");
}
