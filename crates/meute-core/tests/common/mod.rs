#![allow(dead_code, reason = "each test crate uses a subset of the helpers")]
//! Helpers shared by the integration tests of `meute-core`.

use meute_core::actor::{Actor, Author, Channel};
use meute_core::db::Db;
use meute_core::project::ProjectId;
use meute_core::task::{NewTask, Priority};

/// Gives `db` a fixed clock (2026-10-14T08:30:00Z).
#[expect(
    clippy::unwrap_used,
    reason = "shared test helper, not itself a #[test] function"
)]
pub fn clocked(db: Db) -> Db {
    db.with_clock(|| "2026-10-14T08:30:00Z".parse().unwrap())
}

/// An in-memory database with the fixed clock.
#[expect(
    clippy::unwrap_used,
    reason = "shared test helper, not itself a #[test] function"
)]
pub fn test_db() -> Db {
    clocked(Db::open_in_memory().unwrap())
}

/// The user acting from the CLI, without a session.
pub fn user() -> Actor {
    Actor {
        author: Author::User,
        channel: Channel::Cli,
        session_id: None,
    }
}

/// Claude acting through MCP from session `s-1`.
pub fn claude() -> Actor {
    Actor {
        author: Author::Claude,
        channel: Channel::Mcp,
        session_id: Some("s-1".into()),
    }
}

/// A normal-priority task without description or due date.
pub fn new_task(title: &str, project_id: Option<ProjectId>) -> NewTask {
    NewTask {
        title: title.into(),
        description: String::new(),
        priority: Priority::Normal,
        due: None,
        project_id,
    }
}
