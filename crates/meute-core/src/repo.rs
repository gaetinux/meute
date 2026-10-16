//! Repository domain types.

use std::fmt;
use std::path::PathBuf;

use jiff::Timestamp;

use serde::{Deserialize, Serialize};

/// Identifier of a discovered repository.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct RepoId(pub i64);

impl fmt::Display for RepoId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

/// A repository known to meute.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Repo {
    /// Identifier.
    pub id: RepoId,
    /// Canonical path.
    pub path: PathBuf,
    /// Directory name.
    pub name: String,
    /// Detected kind identifier (e.g. `rust`).
    pub kind: Option<String>,
    /// When the repository was first discovered.
    pub discovered_at: Timestamp,
}

/// A repository found by a scan, to register.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NewRepo {
    /// Canonical path.
    pub path: PathBuf,
    /// Directory name.
    pub name: String,
    /// Detected kind identifier.
    pub kind: Option<String>,
}
