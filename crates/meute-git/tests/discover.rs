//! Discovery tests on simulated repositories (no `git` call).
#![expect(
    clippy::unwrap_used,
    reason = "test helpers sit outside #[test] fns, where clippy.toml does not allow unwrap"
)]
use meute_git::{RepoKind, detect_kind, discover, expand_home};
use std::fs;
use std::path::{Path, PathBuf};
use tempfile::TempDir;

fn touch(dir: &Path, file: &str, text: &str) {
    fs::create_dir_all(dir).unwrap();
    fs::write(dir.join(file), text).unwrap();
}

fn repo(dir: &Path) {
    fs::create_dir_all(dir.join(".git")).unwrap();
}

fn tmp() -> (TempDir, PathBuf) {
    let t = tempfile::tempdir().unwrap();
    let r = t.path().canonicalize().unwrap().join("r");
    fs::create_dir_all(&r).unwrap();
    (t, r)
}

fn names(r: &[meute_git::DiscoveredRepo]) -> Vec<String> {
    r.iter().map(|x| x.name.clone()).collect()
}

#[test]
fn detect_kind_rules() {
    let t = tempfile::tempdir().unwrap();
    let d = |n: &str| t.path().join(n);
    assert_eq!(detect_kind(t.path()), None);
    touch(&d("rust"), "Cargo.toml", "");
    assert_eq!(detect_kind(&d("rust")), Some(RepoKind::Rust));
    touch(&d("ng"), "package.json", "{}");
    touch(&d("ng"), "angular.json", "{}");
    assert_eq!(detect_kind(&d("ng")), Some(RepoKind::Angular));
    touch(&d("node"), "package.json", "{}");
    assert_eq!(detect_kind(&d("node")), Some(RepoKind::Node));
    touch(&d("fa"), "pyproject.toml", "dependencies = [\"fastapi\"]");
    assert_eq!(detect_kind(&d("fa")), Some(RepoKind::FastApi));
    touch(&d("fa2"), "requirements.txt", "fastapi==0.1\n");
    assert_eq!(detect_kind(&d("fa2")), Some(RepoKind::FastApi));
    touch(&d("py"), "pyproject.toml", "[project]");
    assert_eq!(detect_kind(&d("py")), Some(RepoKind::Python));
    touch(&d("py2"), "requirements.txt", "requests");
    assert_eq!(detect_kind(&d("py2")), Some(RepoKind::Python));
    touch(&d("py3"), "setup.py", "");
    assert_eq!(detect_kind(&d("py3")), Some(RepoKind::Python));
    touch(&d("both"), "Cargo.toml", "");
    touch(&d("both"), "package.json", "{}");
    assert_eq!(detect_kind(&d("both")), Some(RepoKind::Rust));
}

#[test]
fn repo_kind_ids() {
    assert_eq!(RepoKind::Rust.id(), "rust");
    assert_eq!(RepoKind::Angular.id(), "angular");
    assert_eq!(RepoKind::Node.id(), "node");
    assert_eq!(RepoKind::FastApi.id(), "fastapi");
    assert_eq!(RepoKind::Python.id(), "python");
}

#[test]
fn finds_repos_up_to_depth_three() {
    let (_t, r) = tmp();
    repo(&r.join("a"));
    repo(&r.join("x/b"));
    repo(&r.join("x/y/c"));
    repo(&r.join("x/y/z/d"));
    let found = discover(std::slice::from_ref(&r), 3);
    assert_eq!(names(&found), ["a", "b", "c"]);
}

#[test]
fn root_itself_can_be_a_repo() {
    let (_t, r) = tmp();
    repo(&r);
    touch(&r, "Cargo.toml", "");
    let found = discover(std::slice::from_ref(&r), 3);
    assert_eq!(found.len(), 1);
    assert_eq!(found[0].path, r);
    assert_eq!(found[0].name, "r");
    assert_eq!(found[0].kind, Some(RepoKind::Rust));
}

#[test]
fn does_not_descend_into_repos() {
    let (_t, r) = tmp();
    repo(&r.join("a"));
    repo(&r.join("a/sub"));
    assert_eq!(names(&discover(&[r], 3)), ["a"]);
}

fn worktree_setup(r: &Path, relative: bool) {
    repo(&r.join("meute"));
    fs::create_dir_all(r.join("meute/.git/worktrees/feat")).unwrap();
    let wt = r.join("meute.worktrees/feat");
    let target = if relative {
        "../../meute/.git/worktrees/feat".to_string()
    } else {
        r.join("meute/.git/worktrees/feat").display().to_string()
    };
    touch(&wt, ".git", &format!("gitdir: {target}\n"));
}

#[test]
fn worktrees_attach_to_their_main_repo() {
    for relative in [false, true] {
        let (_t, r) = tmp();
        worktree_setup(&r, relative);
        let found = discover(std::slice::from_ref(&r), 3);
        assert_eq!(names(&found), ["meute"], "relative={relative}");
        assert_eq!(found[0].worktrees, [r.join("meute.worktrees/feat")]);
    }
}

#[test]
fn orphan_worktree_is_ignored() {
    let (_t, r) = tmp();
    let gone = r.join("gone/.git/worktrees/w");
    touch(
        &r.join("wt"),
        ".git",
        &format!("gitdir: {}\n", gone.display()),
    );
    assert!(discover(&[r], 3).is_empty());
}

#[test]
fn submodule_git_file_is_ignored() {
    let (_t, r) = tmp();
    repo(&r.join("main"));
    touch(&r.join("sub"), ".git", "gitdir: ../main/.git/modules/sub\n");
    assert_eq!(names(&discover(&[r], 3)), ["main"]);
}

#[test]
fn missing_root_and_symlink_loop_are_harmless() {
    let (t, r) = tmp();
    assert!(discover(&[t.path().join("absent")], 3).is_empty());
    repo(&r.join("a"));
    std::os::unix::fs::symlink(&r, r.join("loop")).unwrap();
    assert_eq!(names(&discover(&[r], 3)), ["a"]);
}

#[test]
fn hidden_node_modules_and_target_are_skipped() {
    let (_t, r) = tmp();
    repo(&r.join(".hidden/a"));
    repo(&r.join("node_modules/b"));
    repo(&r.join("target/c"));
    repo(&r.join("ok"));
    assert_eq!(names(&discover(&[r], 3)), ["ok"]);
}

#[test]
fn duplicate_roots_give_one_result() {
    let (_t, r) = tmp();
    repo(&r.join("a"));
    assert_eq!(discover(&[r.clone(), r], 3).len(), 1);
}

#[test]
fn expand_home_cases() {
    let h = Path::new("/home/u");
    assert_eq!(expand_home("~", Some(h)), PathBuf::from("/home/u"));
    assert_eq!(expand_home("~/git", Some(h)), PathBuf::from("/home/u/git"));
    assert_eq!(expand_home("/abs", Some(h)), PathBuf::from("/abs"));
    assert_eq!(expand_home("~autre", Some(h)), PathBuf::from("~autre"));
    assert_eq!(expand_home("~/git", None), PathBuf::from("~/git"));
    assert_eq!(expand_home("~", None), PathBuf::from("~"));
}
