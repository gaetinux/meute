//! Projects group tasks.

use jiff::Timestamp;
use serde::{Deserialize, Serialize};

/// Identifier of a project.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ProjectId(pub i64);

/// A project with the instructions given to Claude sessions.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Project {
    /// Identifier.
    pub id: ProjectId,
    /// Unique name.
    pub name: String,
    /// Free-form description.
    pub description: String,
    /// Instructions injected into Claude sessions of this project.
    pub instructions: String,
    /// Creation instant.
    pub created_at: Timestamp,
}
