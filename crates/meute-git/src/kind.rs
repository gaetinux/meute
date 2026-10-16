//! Project kind detection.
use std::path::Path;

/// Kind of project found in a repository.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RepoKind {
    /// Cargo project.
    Rust,
    /// Angular workspace.
    Angular,
    /// Node.js project.
    Node,
    /// FastAPI project.
    FastApi,
    /// Other Python project.
    Python,
}

impl RepoKind {
    /// Stable identifier.
    pub fn id(self) -> &'static str {
        match self {
            Self::Rust => "rust",
            Self::Angular => "angular",
            Self::Node => "node",
            Self::FastApi => "fastapi",
            Self::Python => "python",
        }
    }
}

/// Detects the kind of project in `dir`.
pub fn detect_kind(dir: &Path) -> Option<RepoKind> {
    let has = |name: &str| dir.join(name).is_file();
    let mentions_fastapi = |name: &str| {
        std::fs::read_to_string(dir.join(name))
            .is_ok_and(|text| text.to_lowercase().contains("fastapi"))
    };
    if has("Cargo.toml") {
        Some(RepoKind::Rust)
    } else if has("angular.json") {
        Some(RepoKind::Angular)
    } else if has("package.json") {
        Some(RepoKind::Node)
    } else if mentions_fastapi("pyproject.toml") || mentions_fastapi("requirements.txt") {
        Some(RepoKind::FastApi)
    } else if has("pyproject.toml") || has("requirements.txt") || has("setup.py") {
        Some(RepoKind::Python)
    } else {
        None
    }
}
