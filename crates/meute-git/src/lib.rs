//! Git repository discovery for meute (std only).
#![warn(missing_docs)]

mod discover;
mod kind;

pub use discover::{DEFAULT_DEPTH, DiscoveredRepo, discover, expand_home};
pub use kind::{RepoKind, detect_kind};
