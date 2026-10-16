//! Repository discovery.
use crate::kind::{RepoKind, detect_kind};
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

/// Default scan depth.
pub const DEFAULT_DEPTH: usize = 3;

/// A repository found on disk.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DiscoveredRepo {
    /// Canonical path.
    pub path: PathBuf,
    /// Directory name.
    pub name: String,
    /// Detected kind.
    pub kind: Option<RepoKind>,
    /// Linked worktrees.
    pub worktrees: Vec<PathBuf>,
}

/// Directories never scanned besides hidden ones.
const SKIPPED: [&str; 2] = ["node_modules", "target"];

/// Result of a walk: main repositories and `(main repo path, worktree path)` links.
#[derive(Default)]
struct Found {
    repos: BTreeSet<PathBuf>,
    worktrees: Vec<(PathBuf, PathBuf)>,
}

/// Discovers repositories under `roots`, sorted by path, without duplicates.
///
/// Missing or unreadable directories are ignored and symlinks are never followed.
pub fn discover(roots: &[PathBuf], max_depth: usize) -> Vec<DiscoveredRepo> {
    let mut found = Found::default();
    for root in roots {
        if let Ok(root) = root.canonicalize() {
            walk(&root, 0, max_depth, &mut found);
        }
    }
    found
        .repos
        .iter()
        .filter_map(|path| {
            let name = path.file_name()?.to_str()?.to_owned();
            let mut worktrees: Vec<PathBuf> = found
                .worktrees
                .iter()
                .filter(|(main, _)| main == path)
                .map(|(_, wt)| wt.clone())
                .collect();
            worktrees.sort();
            worktrees.dedup();
            Some(DiscoveredRepo {
                path: path.clone(),
                name,
                kind: detect_kind(path),
                worktrees,
            })
        })
        .collect()
}

fn walk(dir: &Path, depth: usize, max_depth: usize, found: &mut Found) {
    let git = dir.join(".git");
    if let Ok(meta) = std::fs::symlink_metadata(&git) {
        if meta.is_dir() {
            found.repos.insert(dir.to_path_buf());
        } else if meta.is_file() {
            if let Some(main) = main_repo_of_worktree(dir, &git) {
                found.worktrees.push((main, dir.to_path_buf()));
            }
        }
        return;
    }
    if depth >= max_depth {
        return;
    }
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let Ok(file_type) = entry.file_type() else {
            continue;
        };
        let name = entry.file_name();
        let Some(name) = name.to_str() else {
            continue;
        };
        if file_type.is_dir() && !name.starts_with('.') && !SKIPPED.contains(&name) {
            walk(&entry.path(), depth + 1, max_depth, found);
        }
    }
}

/// Returns the main repository path when `git_file` points to `<main>/.git/worktrees/<name>`.
fn main_repo_of_worktree(dir: &Path, git_file: &Path) -> Option<PathBuf> {
    let text = std::fs::read_to_string(git_file).ok()?;
    let target = text
        .lines()
        .find_map(|line| line.strip_prefix("gitdir:"))?
        .trim();
    let admin = dir.join(target).canonicalize().ok()?;
    let worktrees_dir = admin.parent()?;
    let git_dir = worktrees_dir.parent()?;
    if worktrees_dir.file_name()? != "worktrees" || git_dir.file_name()? != ".git" {
        return None;
    }
    git_dir.parent().map(Path::to_path_buf)
}

/// Expands a leading `~` or `~/` using `home`; anything else is returned unchanged.
pub fn expand_home(root: &str, home: Option<&Path>) -> PathBuf {
    match (home, root) {
        (Some(home), "~") => home.to_path_buf(),
        (Some(home), _) => root
            .strip_prefix("~/")
            .map_or_else(|| PathBuf::from(root), |rest| home.join(rest)),
        (None, _) => PathBuf::from(root),
    }
}
